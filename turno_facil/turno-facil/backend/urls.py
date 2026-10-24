from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from turnos import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='turnos/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Cliente
    path('', views.inicio, name='inicio'),
    path('solicitar/', views.solicitar_turno, name='solicitar_turno'),
    path('consultar/', views.consultar_turno, name='consultar_turno'),
    path('turno/<str:codigo>/', views.detalle_turno, name='detalle_turno'),

    # Operador (acciones solo por POST)
    path('panel/', views.panel_turnos, name='panel_turnos'),
    path('panel/accion/<int:turno_id>/<str:accion>/', views.accion_turno, name='accion_turno'),
    path('panel/mostrador/', views.crear_mostrador, name='crear_mostrador'),
    path('panel/siguiente/', views.llamar_siguiente, name='llamar_siguiente'),
    path('panel/estadisticas/', views.estadisticas, name='estadisticas'),

    # Pantalla pública + API en vivo
    path('pantalla/', views.pantalla_publica, name='pantalla_publica'),
    path('api/estado/', views.api_estado, name='api_estado'),
    path('api/turno/<str:codigo>/', views.api_turno, name='api_turno'),
]
