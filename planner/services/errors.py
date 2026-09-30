class PlannerError(Exception):
    status = 400


class LocationNotFound(PlannerError):
    status = 404


class OutsideUnitedStates(PlannerError):
    status = 400


class NoDrivingRoute(PlannerError):
    status = 404


class RouteUnavailable(PlannerError):
    status = 502


class DestinationUnreachable(PlannerError):
    status = 422
