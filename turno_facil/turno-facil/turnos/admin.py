import csv
from datetime import timedelta

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html

from .models import Turno, Servicio, Puesto, Estado, Prioridad, rango_hoy

admin.site.site_header = 'TurnoFácil · Taller'
admin.site.site_title = 'TurnoFácil'
admin.site.index_title = 'Administración del taller'

COLOR_ESTADO = {
    Estado.PENDIENTE: '#0aa5b8', Estado.ATENDIENDO: '#d98a00', Estado.ATENDIDO: '#12a36b',
    Estado.CANCELADO: '#d63c52', Estado.AUSENTE: '#6b7c93',
}
COLOR_PRIORIDAD = {Prioridad.NORMAL: '#6b7c93', Prioridad.ALTA: '#d98a00', Prioridad.URGENTE: '#d63c52'}


def _insignia(texto, color):
    return format_html(
        '<span style="color:{0};border:1px solid {0};border-radius:99px;padding:1px 10px;font-weight:600;white-space:nowrap">{1}</span>',
        color, texto)


class FechaFiltro(admin.SimpleListFilter):
    title = 'fecha'
    parameter_name = 'cuando'

    def lookups(self, request, model_admin):
        return [('hoy', 'Hoy'), ('ayer', 'Ayer'), ('semana', 'Últimos 7 días'), ('mes', 'Últimos 30 días')]

    def queryset(self, request, queryset):
        inicio, fin = rango_hoy()
        rangos = {
            'hoy': (inicio, fin), 'ayer': (inicio - timedelta(days=1), inicio),
            'semana': (inicio - timedelta(days=6), fin), 'mes': (inicio - timedelta(days=29), fin),
        }
        if self.value() in rangos:
            desde, hasta = rangos[self.value()]
            return queryset.filter(fecha__gte=desde, fecha__lt=hasta)
        return queryset


def _celda_segura(valor):
    """Evita que Excel ejecute fórmulas escritas por un cliente (=, +, -, @)."""
    texto = '' if valor is None else str(valor)
    return "'" + texto if texto[:1] in ('=', '+', '-', '@') else texto


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ('prefijo', 'servicio', 'duracion_estimada', 'promedio', 'orden', 'activo', 'turnos_hoy')
    list_editable = ('duracion_estimada', 'orden', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'prefijo')

    @admin.display(description='Servicio', ordering='nombre')
    def servicio(self, obj):
        return format_html('<span style="color:{}">●</span> {} {}', obj.color, obj.icono, obj.nombre)

    @admin.display(description='Promedio real (min)')
    def promedio(self, obj):
        return obj.promedio_real()

    @admin.display(description='Turnos hoy')
    def turnos_hoy(self, obj):
        inicio, fin = rango_hoy()
        return obj.turnos.filter(fecha__gte=inicio, fecha__lt=fin).count()


@admin.register(Puesto)
class PuestoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'operador', 'atiende_servicios', 'ocupado_con', 'activo')
    list_editable = ('activo',)
    list_filter = ('activo',)
    filter_horizontal = ('servicios',)
    raw_id_fields = ('operador',)

    @admin.display(description='Atiende')
    def atiende_servicios(self, obj):
        nombres = [s.prefijo for s in obj.servicios.all()]
        return ', '.join(nombres) if nombres else 'Todos'

    @admin.display(description='Ahora')
    def ocupado_con(self, obj):
        t = obj.turno_actual
        return _insignia(t.etiqueta, COLOR_ESTADO[Estado.ATENDIENDO]) if t else _insignia('Libre', COLOR_ESTADO[Estado.ATENDIDO])


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'cliente', 'placa', 'servicio', 'prioridad_', 'estado_', 'puesto', 'espera', 'hora')
    list_select_related = ('servicio', 'puesto')
    list_filter = (FechaFiltro, 'estado', 'servicio', 'prioridad', 'puesto', 'origen')
    search_fields = ('codigo', 'cliente', 'telefono', 'placa', 'necesidad')
    ordering = ('-fecha',)
    list_per_page = 40
    date_hierarchy = 'fecha'
    save_on_top = True
    readonly_fields = ('codigo', 'fecha', 'llamado_en', 'inicio_atencion', 'fin_atencion', 'llamadas')
    fieldsets = (
        ('Cliente y vehículo', {'fields': ('cliente', 'telefono', 'placa', 'vehiculo')}),
        ('Servicio', {'fields': ('servicio', 'necesidad', 'prioridad', 'origen')}),
        ('Atención', {'fields': ('estado', 'puesto', 'notas')}),
        ('Tiempos', {'classes': ('collapse',),
                     'fields': ('codigo', 'fecha', 'llamado_en', 'inicio_atencion', 'fin_atencion', 'llamadas')}),
    )
    actions = ['llamar', 'rellamar', 'finalizar', 'cancelar', 'ausente', 'devolver', 'subir', 'bajar', 'exportar_csv']

    # ---- columnas ----
    @admin.display(description='Estado', ordering='estado')
    def estado_(self, obj):
        return _insignia(obj.get_estado_display(), COLOR_ESTADO.get(obj.estado, '#6b7c93'))

    @admin.display(description='Prioridad', ordering='prioridad')
    def prioridad_(self, obj):
        return _insignia(obj.get_prioridad_display(), COLOR_PRIORIDAD.get(obj.prioridad, '#6b7c93'))

    @admin.display(description='Espera')
    def espera(self, obj):
        if obj.espera_real is not None:
            return f'{obj.espera_real} min'
        if obj.estado == Estado.PENDIENTE:
            return f'{obj.minutos_esperando()} min (en curso)'
        return '—'

    @admin.display(description='Llegó', ordering='fecha')
    def hora(self, obj):
        return timezone.localtime(obj.fecha).strftime('%d/%m %H:%M')

    # ---- acciones ----
    def _aplicar(self, request, queryset, desde, metodo, verbo, **kwargs):
        hechos = 0
        for t in queryset.filter(estado__in=desde):
            getattr(t, metodo)(**kwargs)
            hechos += 1
        omitidos = queryset.count() - hechos
        if hechos:
            self.message_user(request, f'{hechos} turno(s) {verbo}.', messages.SUCCESS)
        if omitidos:
            self.message_user(request, f'{omitidos} turno(s) omitidos por su estado actual.', messages.WARNING)

    @admin.action(description='Llamar (pasar a atendiendo)')
    def llamar(self, request, queryset):
        self._aplicar(request, queryset, [Estado.PENDIENTE], 'llamar', 'llamados', puesto=None)

    @admin.action(description='Volver a llamar (repite el anuncio)')
    def rellamar(self, request, queryset):
        self._aplicar(request, queryset, [Estado.ATENDIENDO], 'rellamar', 'llamados de nuevo')

    @admin.action(description='Finalizar atención')
    def finalizar(self, request, queryset):
        self._aplicar(request, queryset, [Estado.ATENDIENDO], 'finalizar', 'finalizados')

    @admin.action(description='Cancelar')
    def cancelar(self, request, queryset):
        self._aplicar(request, queryset, [Estado.PENDIENTE, Estado.ATENDIENDO], 'cancelar', 'cancelados')

    @admin.action(description='Marcar como no se presentó')
    def ausente(self, request, queryset):
        self._aplicar(request, queryset, [Estado.PENDIENTE, Estado.ATENDIENDO], 'marcar_ausente', 'marcados como ausentes')

    @admin.action(description='Devolver a la cola de espera')
    def devolver(self, request, queryset):
        self._aplicar(request, queryset, [Estado.ATENDIENDO, Estado.AUSENTE, Estado.CANCELADO],
                      'devolver_a_cola', 'devueltos a la cola')

    @admin.action(description='Subir prioridad')
    def subir(self, request, queryset):
        self._aplicar(request, queryset, [Estado.PENDIENTE], 'subir_prioridad', 'con prioridad aumentada')

    @admin.action(description='Bajar prioridad')
    def bajar(self, request, queryset):
        self._aplicar(request, queryset, [Estado.PENDIENTE], 'bajar_prioridad', 'con prioridad reducida')

    @admin.action(description='Exportar selección a CSV (Excel)')
    def exportar_csv(self, request, queryset):
        respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
        respuesta['Content-Disposition'] = 'attachment; filename="turnos.csv"'
        respuesta.write('\ufeff')  # para que Excel respete las tildes
        w = csv.writer(respuesta)
        w.writerow(['Código', 'Cliente', 'Teléfono', 'Placa', 'Servicio', 'Prioridad', 'Estado', 'Puesto',
                    'Llegó', 'Espera (min)', 'Atención (min)', 'Necesidad'])
        for t in queryset.select_related('servicio', 'puesto'):
            w.writerow([_celda_segura(x) for x in [
                t.codigo, t.cliente, t.telefono, t.placa, t.servicio or '', t.get_prioridad_display(),
                t.get_estado_display(), t.puesto or '', timezone.localtime(t.fecha).strftime('%Y-%m-%d %H:%M'),
                t.espera_real if t.espera_real is not None else '',
                t.duracion_atencion if t.duracion_atencion is not None else '', t.necesidad]])
        return respuesta
