import zlib
from collections import Counter

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Turno, Servicio, Puesto, Estado, Prioridad, Origen, rango_hoy, ESPERA_POR_DEFECTO

MOSTRAR_NOMBRE = getattr(settings, 'TURNOS_MOSTRAR_NOMBRE', True)  # en la pantalla pública


def _buscar(codigo):
    """Acepta 'A-001' o solo el número. Repara turnos antiguos sin código."""
    codigo = (codigo or '').strip().upper()
    qs = Turno.objects.select_related('servicio', 'puesto')
    turno = qs.filter(codigo=codigo).order_by('-fecha').first() if codigo else None
    if not turno and codigo.isdigit():
        turno = qs.filter(numero=int(codigo)).order_by('-fecha').first()
    if turno and not turno.codigo:
        turno.codigo = f"T-{turno.numero:03d}"
        turno.save(update_fields=['codigo'])
    return turno


def _huella():
    """Cambia cada vez que se mueve la cola. Permite refrescar el panel solo cuando hace falta."""
    filas = Turno.objects.filter(estado__in=[Estado.PENDIENTE, Estado.ATENDIENDO]) \
        .order_by('id').values_list('id', 'estado', 'llamadas', 'prioridad')
    return format(zlib.crc32(repr(list(filas)).encode()), 'x')


# ------------------------------------------------------------------ CLIENTE
def inicio(request):
    cola = Turno.cola_lista()
    _, espera_nuevo = Turno.estimar(cola)
    return render(request, 'turnos/inicio.html', {
        'en_espera': len(cola),
        'espera_aprox': espera_nuevo,
        'servicios': Servicio.objects.filter(activo=True),
        'atendiendo': Turno.objects.filter(estado=Estado.ATENDIENDO).select_related('puesto'),
    })


def solicitar_turno(request):
    servicios = Servicio.objects.filter(activo=True)
    if request.method == 'POST':
        cliente = request.POST.get('cliente', '').strip()
        if not cliente:
            messages.error(request, 'Escribe tu nombre para generar el turno.')
            return render(request, 'turnos/solicitar.html', {'servicios': servicios})

        telefono = request.POST.get('telefono', '').strip()[:20]
        inicio_dia, fin_dia = rango_hoy()
        if telefono:  # evita turnos duplicados desde el mismo celular
            abierto = Turno.objects.filter(
                telefono=telefono, estado__in=[Estado.PENDIENTE, Estado.ATENDIENDO],
                fecha__gte=inicio_dia, fecha__lt=fin_dia,
            ).first()
            if abierto:
                messages.info(request, f'Ya tienes el turno {abierto.codigo} activo. Te llevamos a él.')
                return redirect('detalle_turno', codigo=abierto.codigo)

        turno = Turno.crear(
            servicio=servicios.filter(pk=request.POST.get('servicio')).first(),
            cliente=cliente[:100],
            telefono=telefono,
            placa=request.POST.get('placa', '').strip()[:10],
            necesidad=request.POST.get('necesidad', '').strip(),
            prioridad=Prioridad.ALTA if request.POST.get('prioritario') else Prioridad.NORMAL,
            origen=Origen.WEB,
        )
        return redirect('detalle_turno', codigo=turno.codigo)  # evita reenvío al recargar

    return render(request, 'turnos/solicitar.html', {'servicios': servicios})


def consultar_turno(request):
    if request.method == 'POST':
        turno = _buscar(request.POST.get('numero'))
        if turno and turno.codigo:
            return redirect('detalle_turno', codigo=turno.codigo)
        messages.error(request, 'No encontramos ese turno. Revisa el código, por ejemplo A-012.')
    return render(request, 'turnos/consultar.html')


def detalle_turno(request, codigo):
    turno = _buscar(codigo)
    if not turno:
        raise Http404
    delante, espera = turno.posicion()
    return render(request, 'turnos/detalle.html', {'turno': turno, 'personas_delante': delante, 'espera': espera})


def api_turno(request, codigo):
    turno = _buscar(codigo)
    if not turno:
        return JsonResponse({'error': 'no encontrado'}, status=404)
    delante, espera = turno.posicion()
    return JsonResponse({
        'codigo': turno.codigo, 'estado': turno.estado, 'delante': delante, 'espera': espera,
        'puesto': turno.puesto.nombre if turno.puesto else None,
    })


# ------------------------------------------------------------------ PANTALLA
def pantalla_publica(request):
    return render(request, 'turnos/pantalla.html')


def _primer_nombre(cliente):
    partes = (cliente or '').split()
    return partes[0] if (partes and MOSTRAR_NOMBRE) else ''


def api_estado(request):
    actuales = list(
        Turno.objects.filter(estado=Estado.ATENDIENDO).select_related('puesto', 'servicio').order_by('-llamado_en')
    )
    cola = Turno.cola_lista()
    esperas, espera_nuevo = Turno.estimar(cola)
    return JsonResponse({
        'actuales': [{
            'id': t.id, 'codigo': t.etiqueta, 'cliente': _primer_nombre(t.cliente),
            'puesto': t.puesto.nombre if t.puesto else 'Recepción',
            'servicio': t.servicio.nombre if t.servicio else '',
            'marca': int(t.llamado_en.timestamp() * 1000) if t.llamado_en else 0,  # cambia al re-llamar
            'llamadas': t.llamadas,
        } for t in actuales],
        'proximos': [{
            'codigo': t.etiqueta, 'servicio': t.servicio.nombre if t.servicio else '',
            'prioridad': t.prioridad_efectiva(), 'espera': e,
        } for t, e in list(zip(cola, esperas))[:6]],
        'en_espera': len(cola),
        'espera_nuevo': espera_nuevo,
        'huella': _huella(),
    })


# ------------------------------------------------------------------ OPERADOR
@login_required
def panel_turnos(request):
    inicio_dia, fin_dia = rango_hoy()
    base = Turno.objects.filter(fecha__gte=inicio_dia, fecha__lt=fin_dia)
    cola = Turno.cola_lista()
    esperas, espera_nuevo = Turno.estimar(cola)

    atendiendo = list(Turno.objects.filter(estado=Estado.ATENDIENDO).select_related('servicio', 'puesto'))
    por_puesto = {}
    for t in atendiendo:
        por_puesto.setdefault(t.puesto_id, []).append(t)

    puestos = list(Puesto.objects.filter(activo=True).prefetch_related('servicios'))
    tarjetas = []
    for p in puestos:
        lista = por_puesto.pop(p.id, [])
        tarjetas.append({'puesto': p, 'turno': lista[0] if lista else None, 'extra': lista[1:]})
    sin_puesto = por_puesto.pop(None, [])
    huerfanos = [t for lista in por_puesto.values() for t in lista]  # puestos desactivados
    if not puestos:
        tarjetas = [{'puesto': None, 'turno': sin_puesto[0] if sin_puesto else None, 'extra': sin_puesto[1:]}]
        sin_puesto = []

    return render(request, 'turnos/panel.html', {
        'tarjetas': tarjetas,
        'sin_puesto': sin_puesto + huerfanos,
        'cola': list(zip(cola, esperas)),
        'puestos': puestos,
        'mi_puesto': next((p.id for p in puestos if p.operador_id == request.user.id), None),
        'servicios': Servicio.objects.filter(activo=True),
        'recientes': base.filter(estado__in=[Estado.ATENDIDO, Estado.CANCELADO, Estado.AUSENTE])
                         .select_related('servicio').order_by('-fin_atencion')[:8],
        'total': base.count(),
        'pendientes': len(cola),
        'atendiendo_n': len(atendiendo),
        'atendidos': base.filter(estado=Estado.ATENDIDO).count(),
        'ausentes': base.filter(estado=Estado.AUSENTE).count(),
        'espera_nuevo': espera_nuevo,
        'huella': _huella(),
    })


# acción -> (estados desde los que se permite, mensaje de éxito)
ACCIONES = {
    'llamar':    ({Estado.PENDIENTE}, 'Llamaste al turno {c}.'),
    'rellamar':  ({Estado.ATENDIENDO}, 'Volviste a llamar al turno {c}.'),
    'finalizar': ({Estado.ATENDIENDO}, 'Turno {c} finalizado.'),
    'cancelar':  ({Estado.PENDIENTE, Estado.ATENDIENDO}, 'Turno {c} cancelado.'),
    'ausente':   ({Estado.PENDIENTE, Estado.ATENDIENDO}, 'Turno {c} marcado como ausente.'),
    'devolver':  ({Estado.ATENDIENDO, Estado.AUSENTE, Estado.CANCELADO}, 'Turno {c} volvió a la cola.'),
    'subir':     ({Estado.PENDIENTE}, 'Subiste la prioridad del turno {c}.'),
    'bajar':     ({Estado.PENDIENTE}, 'Bajaste la prioridad del turno {c}.'),
}


@login_required
@require_POST
def accion_turno(request, turno_id, accion):
    if accion not in ACCIONES:
        raise Http404
    permitidos, mensaje = ACCIONES[accion]
    with transaction.atomic():
        turno = get_object_or_404(Turno.objects.select_for_update(), pk=turno_id)
        if turno.estado not in permitidos:
            messages.warning(request, f'El turno {turno.etiqueta} ya cambió de estado. Revisa el panel.')
            return redirect('panel_turnos')

        if accion == 'llamar':
            puesto = Puesto.objects.filter(pk=request.POST.get('puesto'), activo=True).first()
            if puesto:  # el puesto cierra lo que estaba atendiendo antes de tomar otro
                for t in Turno.objects.select_for_update().filter(estado=Estado.ATENDIENDO, puesto=puesto):
                    t.finalizar()
            turno.llamar(puesto)
        elif accion == 'rellamar':
            turno.rellamar()
        elif accion == 'finalizar':
            turno.finalizar()
        elif accion == 'cancelar':
            turno.cancelar()
        elif accion == 'ausente':
            turno.marcar_ausente()
        elif accion == 'devolver':
            turno.devolver_a_cola()
        elif accion == 'subir':
            turno.subir_prioridad()
        elif accion == 'bajar':
            turno.bajar_prioridad()
        messages.success(request, mensaje.format(c=turno.etiqueta))
    return redirect('panel_turnos')


@login_required
@require_POST
def llamar_siguiente(request):
    puesto = Puesto.objects.filter(pk=request.POST.get('puesto'), activo=True).first()
    with transaction.atomic():
        for t in Turno.objects.select_for_update().filter(estado=Estado.ATENDIENDO, puesto=puesto):
            t.finalizar()
        candidato = Turno.siguiente_para(puesto)
        turno = Turno.objects.select_for_update().filter(pk=candidato.pk).first() if candidato else None
        if turno and turno.estado == Estado.PENDIENTE:
            turno.llamar(puesto)
            messages.success(request, f'Llamaste al turno {turno.etiqueta}.')
        else:
            messages.info(request, 'No hay turnos en espera para este puesto.')
    return redirect('panel_turnos')


@login_required
@require_POST
def crear_mostrador(request):
    """Registra a un cliente que llegó en persona."""
    try:
        prioridad = int(request.POST.get('prioridad', 0))
    except ValueError:
        prioridad = 0
    if prioridad not in Prioridad.values:
        prioridad = 0
    turno = Turno.crear(
        servicio=Servicio.objects.filter(pk=request.POST.get('servicio'), activo=True).first(),
        cliente=(request.POST.get('cliente', '').strip() or 'Cliente de mostrador')[:100],
        telefono=request.POST.get('telefono', '').strip()[:20],
        placa=request.POST.get('placa', '').strip()[:10],
        necesidad=request.POST.get('necesidad', '').strip(),
        prioridad=prioridad,
        origen=Origen.MOSTRADOR,
    )
    messages.success(request, f'Registraste el turno {turno.etiqueta} para {turno.cliente}.')
    return redirect('panel_turnos')


@login_required
def estadisticas(request):
    inicio_dia, fin_dia = rango_hoy()
    dia = Turno.objects.filter(fecha__gte=inicio_dia, fecha__lt=fin_dia)
    atendidos = list(dia.filter(estado=Estado.ATENDIDO))
    esperas = [t.espera_real for t in atendidos if t.espera_real is not None]
    duraciones = [t.duracion_atencion for t in atendidos if t.duracion_atencion is not None]
    por_hora = Counter(timezone.localtime(t.fecha).hour for t in dia)
    horas = [{'h': h, 'n': por_hora.get(h, 0)} for h in range(7, 20)]
    return render(request, 'turnos/estadisticas.html', {
        'total': dia.count(),
        'atendidos': len(atendidos),
        'cancelados': dia.filter(estado=Estado.CANCELADO).count(),
        'ausentes': dia.filter(estado=Estado.AUSENTE).count(),
        'espera_prom': round(sum(esperas) / len(esperas)) if esperas else 0,
        'atencion_prom': round(sum(duraciones) / len(duraciones)) if duraciones else 0,
        'por_servicio': dia.values('servicio__nombre').annotate(n=Count('id')).order_by('-n'),
        'por_puesto': dia.filter(estado=Estado.ATENDIDO).values('puesto__nombre').annotate(n=Count('id')).order_by('-n'),
        'horas': horas,
        'max_hora': max([x['n'] for x in horas] + [1]),
    })
