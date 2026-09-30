from django.urls import path

from planner import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/v1/health/", views.health, name="health"),
    path("api/v1/route/", views.plan_route, name="plan-route"),
    path("api/v1/route/<str:plan_id>/map/", views.route_map, name="route-map"),
]
