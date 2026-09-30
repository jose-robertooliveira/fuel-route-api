from django.apps import AppConfig


class PlannerConfig(AppConfig):
    name = "planner"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from planner.services.stations import load_stations

        load_stations()
