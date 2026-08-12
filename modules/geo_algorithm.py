"""
Geospatial Matching Algorithm Module
-----------------------------------
Matches user locations with store-visit tasks using PostGIS, via GeoDjango's
`PointField` (geography type) and `ST_DWithin` / `Distance`.

Requires:
  - PostgreSQL + PostGIS extension enabled on the database.
  - `django.contrib.gis` in INSTALLED_APPS, DB engine set to
    `django.contrib.gis.db.backends.postgis`.
  - The model passed in as `tasks_queryset` must have a `location`
    `gis_models.PointField(geography=True, spatial_index=True)` column
"""

from typing import Any, Dict, List, Optional
import logging

from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance

logger = logging.getLogger(__name__)

# Default search radius in kilometers
DEFAULT_RADIUS_KM = 10.0
# Maximum allowed radius to prevent unbounded/expensive queries
MAX_RADIUS_KM = 50.0

# Task type priority for sorting (lower number = higher priority)
TASK_TYPE_PRIORITY = {
    "store_visit": 1,  # Highest priority - proximity based
    "watch_video": 2,  # Second priority
    "social_engage": 3,  # Third priority
    "app_download": 4,  # Fourth priority
    "in_app_challenge": 5,  # Fifth priority
    "ugc_task": 6,  # Sixth priority
}


class LocationMatcher:
    """
    Location matching service backed entirely by PostGIS.

    Given a Django queryset of tasks whose model has a `location`
    `PointField(geography=True)`, returns tasks within `radius_km` of the
    user, sorted nearest-first, using a single database query.
    """

    def match_tasks_to_user(
        self,
        tasks_queryset,
        user_lat: float,
        user_lon: float,
        radius_km: float = DEFAULT_RADIUS_KM,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Match and sort tasks based on user location using ST_DWithin.

        Args:
            tasks_queryset: Django queryset of tasks; the underlying model
                must have a `location` PointField(geography=True).
            user_lat (float): User's latitude
            user_lon (float): User's longitude
            radius_km (float): Search radius in kilometers (capped at
                MAX_RADIUS_KM)
            max_results (Optional[int]): Maximum number of results

        Returns:
            List[Dict[str, Any]]: Each dict has "task", "distance_km", and
            "distance_meters", sorted nearest-first. Tasks with no location
            set are naturally excluded.
        """
        if radius_km <= 0:
            logger.warning(f"Invalid radius: {radius_km}km, using default")
            radius_km = DEFAULT_RADIUS_KM
        radius_km = min(radius_km, MAX_RADIUS_KM)

        logger.info(
            f"Location matching (PostGIS): user at ({user_lat}, {user_lon}), "
            f"radius={radius_km}km, max_results={max_results}"
        )

        user_point = Point(float(user_lon), float(user_lat), srid=4326)

        qs = (
            tasks_queryset.filter(location__isnull=False)
            .filter(location__dwithin=(user_point, D(km=radius_km)))
            .annotate(distance=Distance("location", user_point))
            .order_by("distance")
        )

        if max_results and max_results > 0:
            qs = qs[:max_results]

        results = []
        for task in qs:
            distance_km = round(task.distance.km, 2)
            results.append(
                {
                    "task": task,
                    "distance_km": distance_km,
                    "distance_meters": round(distance_km * 1000, 2),
                }
            )
        return results


class TaskSortingStrategy:
    """
    Strategy for sorting mixed task types with geospatial awareness.

    This class implements various sorting strategies to combine
    different task types while prioritizing proximity for store visits.
    """

    @staticmethod
    def sort_tasks_by_priority_and_distance(
        brand_tasks: List[Dict[str, Any]],
        social_tasks: List[Dict[str, Any]],
        inapp_tasks: List[Dict[str, Any]],
        ugc_tasks: List[Dict[str, Any]] = None,
        user_lat: Optional[float] = None,
        user_lon: Optional[float] = None,
        radius_km: float = DEFAULT_RADIUS_KM,
    ) -> List[Dict[str, Any]]:
        """
        Sort all tasks with priority given to nearby store visits.

        This method implements a hybrid sorting strategy:
        1. Store visits are sorted by distance (closest first)
        2. Other tasks are interleaved based on priority
        3. Overall sorting considers both proximity and task type

        Args:
            brand_tasks: List of brand task data (serialized dicts)
            social_tasks: List of social task data (serialized dicts)
            inapp_tasks: List of in-app task data (serialized dicts)
            ugc_tasks: List of UGC task data (serialized dicts)
            user_lat: User's latitude (for store visits)
            user_lon: User's longitude (for store visits)
            radius_km: Search radius for store visits

        Returns:
            List[Dict[str, Any]]: Combined and sorted task list
        """
        all_tasks = []

        # Process brand tasks
        for task_data in brand_tasks:
            # Check if it's a store visit with distance data
            if task_data.get("distance_km") is not None:
                # Store visit with distance already calculated
                task_data["sort_priority"] = 1  # Highest priority for nearby
                all_tasks.append(task_data)
            else:
                # Non-store visit or store visit without location
                task_type = task_data.get("task_type") or task_data.get("type", "other")
                task_data["sort_priority"] = TASK_TYPE_PRIORITY.get(task_type, 10)
                all_tasks.append(task_data)

        # Process social tasks
        for task_data in social_tasks:
            task_data["sort_priority"] = TASK_TYPE_PRIORITY.get("social_engage", 3)
            task_data["distance_km"] = None
            all_tasks.append(task_data)

        # Process in-app tasks
        for task_data in inapp_tasks:
            task_data["sort_priority"] = TASK_TYPE_PRIORITY.get("in_app_challenge", 5)
            task_data["distance_km"] = None
            all_tasks.append(task_data)

        # Process UGC tasks
        for task_data in ugc_tasks or []:
            task_data["sort_priority"] = TASK_TYPE_PRIORITY.get("ugc_task", 6)
            task_data["distance_km"] = None
            all_tasks.append(task_data)

        # Sort by priority, then by distance for store visits
        all_tasks.sort(
            key=lambda x: (
                x.get("sort_priority", 10),
                (
                    x.get("distance_km", float("inf"))
                    if x.get("distance_km") is not None
                    else float("inf")
                ),
            )
        )

        return all_tasks

    @staticmethod
    def interleave_tasks_by_type(
        store_tasks: List[Dict[str, Any]],
        other_tasks: List[Dict[str, Any]],
        max_store_per_cycle: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Interleave store tasks with other task types for balanced feed.

        This ensures users see a mix of task types, not just store visits.

        Args:
            store_tasks: List of store visit tasks (already sorted by distance)
            other_tasks: List of other task types
            max_store_per_cycle: Maximum store tasks before showing other types

        Returns:
            List[Dict[str, Any]]: Interleaved task list
        """
        result = []
        store_idx = 0
        other_idx = 0

        while store_idx < len(store_tasks) or other_idx < len(other_tasks):
            # Add store tasks
            for _ in range(max_store_per_cycle):
                if store_idx < len(store_tasks):
                    result.append(store_tasks[store_idx])
                    store_idx += 1
                else:
                    break

            # Add one other task
            if other_idx < len(other_tasks):
                result.append(other_tasks[other_idx])
                other_idx += 1

        return result


def get_distance_band(distance_km: float) -> str:
    """
    Get a human-readable distance band for a given distance.

    Args:
        distance_km (float): Distance in kilometers

    Returns:
        str: Distance band description
    """
    if distance_km < 1:
        return "Very Close (< 1 km)"
    elif distance_km < 5:
        return "Nearby (1-5 km)"
    elif distance_km < 10:
        return "Moderate (5-10 km)"
    elif distance_km < 25:
        return "Far (10-25 km)"
    else:
        return "Very Far (> 25 km)"


def is_valid_coordinate(lat: float, lon: float) -> bool:
    """
    Validate latitude and longitude coordinates.

    Args:
        lat (float): Latitude value
        lon (float): Longitude value

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        return (
            isinstance(lat, (int, float))
            and isinstance(lon, (int, float))
            and -90 <= lat <= 90
            and -180 <= lon <= 180
        )
    except (TypeError, ValueError):
        return False
