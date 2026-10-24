from datetime import timedelta

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils import timezone

# Un turno "normal" que lleva más de estos minutos esperando se trata como prioridad alta,
# para que nadie se quede atrás indefinidamente. Se puede cambiar en settings.py.
ENVEJECE_MIN = getattr(settings, 'TURNOS_ENVEJECE_MIN', 45)
ESPERA_POR_DEFECTO = 15  # minutos cuando un turno no tiene servicio


def rango_hoy():
    """(inicio, fin) del día local. Funciona en MySQL sin tablas de zona horaria."""
    inicio = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return inicio, inicio + timedelta(days=1)


class Estado(models.TextChoices):
    PENDIENTE = 'pendiente', 'Pendiente'
    ATENDIENDO = 'atendiendo', 'Atendiendo'
    ATENDIDO = 'atendido', 'Atendido'
    CANCELADO = 'cancelado', 'Cancelado'
    AUSENTE = 'ausente', 'No se presentó'


class Prioridad(models.IntegerChoices):
    NORMAL = 0, 'Normal'
    ALTA = 1, 'Alta'
    URGENTE = 2, 'Urgente'


class Origen(models.TextChoices):
    WEB = 'web', 'En línea'
    MOSTRADOR = 'mostrador', 'Mostrador'


class Servicio(models.Model):
    """Tipo de atención del taller. Se administra desde /admin/ sin tocar código."""
    nombre = models.CharField(max_length=60)
    prefijo = models.CharField(max_length=3, unique=True, help_text="Letra del turno, ej: A, B, FR")
    duracion_estimada = models.PositiveIntegerField(default=20, help_text="Minutos")
    icono = models.CharField(max_length=4, default="🔧", help_text="Emoji")
    color = models.CharField(
        max_length=7, default="#35e6ff", help_text="Color en formato #RRGGBB",
        validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$', 'Usa el formato #RRGGBB')],
    )
    orden = models.PositiveSmallIntegerField(default=0, help_text="Menor número aparece primero")
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['orden', 'nombre']

    def __str__(self):
        return f"{self.prefijo} · {self.nombre}"

    def save(self, *args, **kwargs):
        self.prefijo = self.prefijo.strip().upper()
        super().save(*args, **kwargs)

    def promedio_real(self):
        """Promedio de los últimos 30 turnos atendidos; con menos de 3 usa la estimación."""
        recientes = (
            self.turnos.filter(estado=Estado.ATENDIDO, inicio_atencion__isnull=False, fin_atencion__isnull=False)
            .order_by('-fin_atencion')[:30]
        )
        segs = [(t.fin_atencion - t.inicio_atencion).total_seconds() for t in recientes]
        if len(segs) >= 3:
            return max(1, round(sum(segs) / len(segs) / 60))
        return self.duracion_estimada

    @classmethod
    def promedios(cls):
        """{servicio_id: minutos}. Se calcula una vez y se reutiliza."""
        return {s.id: s.promedio_real() for s in cls.objects.all()}


class Puesto(models.Model):
    """Una bahía o mecánico que atiende en paralelo."""
    nombre = models.CharField(max_length=40)
    servicios = models.ManyToManyField(
        Servicio, blank=True, related_name='puestos',
        help_text="Servicios que atiende este puesto. Vacío = atiende todos.",
    )
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='puestos', help_text="Usuario que normalmente atiende aquí",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name_plural = 'puestos'

    def __str__(self):
        return self.nombre

    def atiende(self, servicio_id):
        ids = set(self.servicios.values_list('id', flat=True))
        return not ids or servicio_id is None or servicio_id in ids

    @property
    def turno_actual(self):
        return self.turnos.filter(estado=Estado.ATENDIENDO).order_by('-llamado_en').first()


class Turno(models.Model):
    # Alias para no romper código viejo
    ESTADOS = Estado.choices
    PRIORIDADES = Prioridad.choices

    # Campos originales
    numero = models.IntegerField(editable=False)
    cliente = models.CharField(max_length=100)
    fecha = models.DateTimeField(default=timezone.now)
    necesidad = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)

    # Campos de la primera mejora
    codigo = models.CharField(max_length=12, blank=True, db_index=True)
    telefono = models.CharField(max_length=20, blank=True)
    servicio = models.ForeignKey(Servicio, null=True, blank=True, on_delete=models.SET_NULL, related_name='turnos')
    puesto = models.ForeignKey(Puesto, null=True, blank=True, on_delete=models.SET_NULL, related_name='turnos')
    prioridad = models.IntegerField(choices=Prioridad.choices, default=Prioridad.NORMAL)
    llamado_en = models.DateTimeField(null=True, blank=True)
    inicio_atencion = models.DateTimeField(null=True, blank=True)
    fin_atencion = models.DateTimeField(null=True, blank=True)

    # Campos nuevos
    placa = models.CharField(max_length=10, blank=True)
    vehiculo = models.CharField("vehículo", max_length=60, blank=True, help_text="Marca y modelo")
    notas = models.TextField("notas internas", blank=True, help_text="Solo las ve el personal")
    origen = models.CharField(max_length=10, choices=Origen.choices, default=Origen.WEB)
    llamadas = models.PositiveSmallIntegerField(default=0, help_text="Veces que se llamó al cliente")

    class Meta:
        ordering = ['-prioridad', 'fecha']
        indexes = [models.Index(fields=['estado', '-prioridad', 'fecha'])]

    def __str__(self):
        return f"{self.etiqueta} - {self.cliente}"

    @property
    def etiqueta(self):
        return self.codigo or str(self.numero)

    # ------------------------------------------------------------ guardado y numeración
    @classmethod
    def siguiente_numero(cls, servicio):
        """Numera por servicio y por día. Debe llamarse dentro de una transacción."""
        inicio, fin = rango_hoy()
        ultimo = (
            cls.objects.select_for_update()
            .filter(servicio=servicio, fecha__gte=inicio, fecha__lt=fin)
            .order_by('-numero').values_list('numero', flat=True).first()
        )
        return (ultimo or 0) + 1

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.numero is None:
                self.numero = self.siguiente_numero(self.servicio)
            if not self.codigo:
                prefijo = self.servicio.prefijo if self.servicio_id else 'T'
                self.codigo = f"{prefijo}-{self.numero:03d}"
            if self.placa:
                self.placa = self.placa.strip().upper()
            super().save(*args, **kwargs)

    @classmethod
    def crear(cls, servicio, **datos):
        turno = cls(servicio=servicio, **datos)
        turno.save()
        return turno

    # ------------------------------------------------------------ cola
    def minutos_esperando(self, ahora=None):
        ahora = ahora or timezone.now()
        return max(0, int((ahora - self.fecha).total_seconds() // 60))

    def prioridad_efectiva(self, ahora=None):
        """Un turno normal que espera demasiado sube a prioridad alta."""
        if self.prioridad == Prioridad.NORMAL and self.minutos_esperando(ahora) >= ENVEJECE_MIN:
            return Prioridad.ALTA
        return self.prioridad

    @property
    def subio_por_espera(self):
        return self.estado == Estado.PENDIENTE and self.prioridad_efectiva() > self.prioridad

    @classmethod
    def cola_lista(cls, servicios_ids=None):
        """Turnos pendientes en el orden real de atención."""
        ahora = timezone.now()
        pendientes = cls.objects.filter(estado=Estado.PENDIENTE).select_related('servicio')
        cola = [
            t for t in pendientes
            if not servicios_ids or t.servicio_id is None or t.servicio_id in servicios_ids
        ]
        cola.sort(key=lambda t: (-t.prioridad_efectiva(ahora), t.fecha))
        return cola

    @classmethod
    def siguiente_para(cls, puesto=None):
        ids = set(puesto.servicios.values_list('id', flat=True)) if puesto else set()
        cola = cls.cola_lista(ids or None)
        return cola[0] if cola else None

    @classmethod
    def estimar(cls, cola):
        """([minutos de espera de cada turno de la cola], minutos para un turno nuevo)."""
        prom = Servicio.promedios()
        puestos = max(1, Puesto.objects.filter(activo=True).count())
        acumulado, esperas = 0, []
        for t in cola:
            esperas.append(round(acumulado / puestos))
            acumulado += prom.get(t.servicio_id, ESPERA_POR_DEFECTO)
        return esperas, round(acumulado / puestos)

    def posicion(self):
        """(turnos delante, minutos estimados)."""
        if self.estado != Estado.PENDIENTE:
            return 0, 0
        cola = self.cola_lista()
        esperas, _ = self.estimar(cola)
        for i, t in enumerate(cola):
            if t.pk == self.pk:
                return i, esperas[i]
        return 0, 0

    def personas_delante(self):
        return self.posicion()[0]

    def espera_estimada(self):
        return self.posicion()[1]

    # ------------------------------------------------------------ transiciones
    def llamar(self, puesto=None):
        ahora = timezone.now()
        self.estado = Estado.ATENDIENDO
        self.llamado_en = self.inicio_atencion = ahora
        self.fin_atencion = None
        self.llamadas = 1
        if puesto:
            self.puesto = puesto
        self.save()

    def rellamar(self):
        """Vuelve a anunciar el turno en la pantalla y por voz."""
        self.llamado_en = timezone.now()
        self.llamadas += 1
        self.save(update_fields=['llamado_en', 'llamadas'])

    def _cerrar(self, estado):
        self.estado = estado
        self.fin_atencion = timezone.now()
        if estado == Estado.ATENDIDO and not self.inicio_atencion:
            self.inicio_atencion = self.llamado_en or self.fin_atencion
        self.save()

    def finalizar(self):
        self._cerrar(Estado.ATENDIDO)

    def cancelar(self):
        self._cerrar(Estado.CANCELADO)

    def marcar_ausente(self):
        self._cerrar(Estado.AUSENTE)

    def devolver_a_cola(self):
        self.estado = Estado.PENDIENTE
        self.puesto = None
        self.llamado_en = self.inicio_atencion = self.fin_atencion = None
        self.llamadas = 0
        self.save()

    def subir_prioridad(self):
        self.prioridad = min(Prioridad.URGENTE, self.prioridad + 1)
        self.save(update_fields=['prioridad'])

    def bajar_prioridad(self):
        self.prioridad = max(Prioridad.NORMAL, self.prioridad - 1)
        self.save(update_fields=['prioridad'])

    # ------------------------------------------------------------ métricas
    @property
    def espera_real(self):
        """Minutos entre llegar y ser llamado."""
        if self.llamado_en:
            return max(0, int((self.llamado_en - self.fecha).total_seconds() // 60))
        return None

    @property
    def duracion_atencion(self):
        if self.inicio_atencion and self.fin_atencion:
            return max(0, int((self.fin_atencion - self.inicio_atencion).total_seconds() // 60))
        return None
