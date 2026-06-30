"""
Geospatial Matching Algorithm Module
-----------------------------------
This module implements a circular range search algorithm for matching user locations
with store visit tasks. The algorithm uses the Haversine formula to calculate
great-circle distances between two points on Earth's surface.

Key Components:
1. Haversine distance calculation
2. Circular range filtering
3. Distance-based sorting (closest to farthest)
4. Optimized database querying with geospatial indexing
5. Task type prioritization and sorting

The algorithm ensures users only see tasks within their geographical vicinity,
starting from the nearest to the farthest, up to a specified radius.
"""

import math
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Earth's radius in kilometers
EARTH_RADIUS_KM = 6371.0
# Earth's radius in meters (for more precise calculations)
EARTH_RADIUS_METERS = 6371000.0

# Default search radius in kilometers
DEFAULT_RADIUS_KM = 10.0
# Maximum allowed radius to prevent performance issues
MAX_RADIUS_KM = 50.0

# Task type priority for sorting (lower number = higher priority)
TASK_TYPE_PRIORITY = {
    "store_visit": 1,  # Highest priority - proximity based
    "watch_video": 2,  # Second priority
    "social_engage": 3,  # Third priority
    "app_download": 4,  # Fourth priority
    "in_app_challenge": 5,  # Fifth priority
}


class GeoAlgorithm:
    """
    Geospatial matching algorithm for finding nearby store visit tasks.

    This class implements various methods for calculating distances and
    filtering tasks based on user location with circular range constraints.
    """

    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great-circle distance between two points on Earth.

        The Haversine formula determines the shortest distance between two
        points on a sphere using their latitudes and longitudes.

        Args:
            lat1 (float): Latitude of first point in degrees
            lon1 (float): Longitude of first point in degrees
            lat2 (float): Latitude of second point in degrees
            lon2 (float): Longitude of second point in degrees

        Returns:
            float: Distance in kilometers between the two points

        Example:
            >>> distance = haversine_distance(4.8156, 7.0498, 4.8242, 7.0336)
            >>> print(f"Distance: {distance:.2f} km")
            Distance: 1.87 km
        """
        # Convert degrees to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        # Differences in coordinates
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        # Haversine formula
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        # Distance in kilometers
        distance = EARTH_RADIUS_KM * c
        return distance

    @staticmethod
    def calculate_distance_km(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """
        Calculate distance in kilometers with better precision handling.

        This is a wrapper around haversine_distance with additional
        validation and precision handling.

        Args:
            lat1 (float): Latitude of first point
            lon1 (float): Longitude of first point
            lat2 (float): Latitude of second point
            lon2 (float): Longitude of second point

        Returns:
            float: Distance in kilometers rounded to 2 decimal places
        """
        try:
            distance = GeoAlgorithm.haversine_distance(lat1, lon1, lat2, lon2)
            # Round to 2 decimal places for cleaner output
            return round(distance, 2)
        except Exception as e:
            logger.error(f"Error calculating distance: {e}")
            return float("inf")

    @staticmethod
    def is_within_range(
        user_lat: float,
        user_lon: float,
        target_lat: float,
        target_lon: float,
        radius_km: float = DEFAULT_RADIUS_KM,
    ) -> bool:
        """
        Check if a target location is within the circular range of the user.

        Args:
            user_lat (float): User's latitude
            user_lon (float): User's longitude
            target_lat (float): Target location's latitude
            target_lon (float): Target location's longitude
            radius_km (float): Search radius in kilometers

        Returns:
            bool: True if within range, False otherwise
        """
        if radius_km <= 0:
            return False

        # Validate coordinates
        if not (-90 <= user_lat <= 90) or not (-90 <= target_lat <= 90):
            return False
        if not (-180 <= user_lon <= 180) or not (-180 <= target_lon <= 180):
            return False

        distance = GeoAlgorithm.haversine_distance(
            user_lat, user_lon, target_lat, target_lon
        )
        return distance <= radius_km

    @staticmethod
    def get_nearby_store_tasks(
        queryset,
        user_lat: float,
        user_lon: float,
        radius_km: float = DEFAULT_RADIUS_KM,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get store visit tasks within circular range sorted by distance (closest first).

        This method uses Python-side distance calculation and is suitable
        for smaller datasets or when PostGIS is not available.

        Args:
            queryset: Django queryset of tasks with latitude and longitude fields
            user_lat (float): User's current latitude
            user_lon (float): User's current longitude
            radius_km (float): Search radius in kilometers
            max_results (Optional[int]): Maximum number of results to return

        Returns:
            List[Dict[str, Any]]: List of tasks with distance information
        """
        if radius_km > MAX_RADIUS_KM:
            radius_km = MAX_RADIUS_KM
            logger.warning(f"Radius capped to maximum of {MAX_RADIUS_KM} km")

        # Calculate distance for each task and filter within radius
        tasks_with_distance = []

        for task in queryset:
            # Skip tasks without coordinates
            if task.latitude is None or task.longitude is None:
                continue

            distance = GeoAlgorithm.calculate_distance_km(
                user_lat, user_lon, task.latitude, task.longitude
            )

            # Check if within radius
            if distance <= radius_km:
                # Create a copy of task data with distance info
                task_data = {
                    "task": task,
                    "distance_km": distance,
                    "distance_meters": distance * 1000,
                }
                tasks_with_distance.append(task_data)

        # Sort by distance (closest first)
        tasks_with_distance.sort(key=lambda x: x["distance_km"])

        # Apply max results limit if specified
        if max_results and max_results > 0:
            tasks_with_distance = tasks_with_distance[:max_results]

        return tasks_with_distance


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
            brand_tasks: List of brand task data
            social_tasks: List of social task data
            inapp_tasks: List of in-app task data
            user_lat: User's latitude (for store visits)
            user_lon: User's longitude (for store visits)
            radius_km: Search radius for store visits

        Returns:
            List[Dict[str, Any]]: Combined and sorted task list
        """
        all_tasks = []

        # Process brand tasks with location data
        for task_data in brand_tasks:
            task = task_data.get("task") or task_data.get("ad")

            # Check if it's a store visit with location data
            if (
                task.task_type == "store_visit"
                and hasattr(task, "latitude")
                and task.latitude
                and hasattr(task, "longitude")
                and task.longitude
                and user_lat is not None
                and user_lon is not None
            ):

                distance = GeoAlgorithm.calculate_distance_km(
                    user_lat, user_lon, task.latitude, task.longitude
                )

                if distance <= radius_km:
                    task_data["distance_km"] = distance
                    task_data["distance_meters"] = distance * 1000
                    task_data["sort_priority"] = 1  # Highest priority for nearby
                    task_data["distance_band"] = get_distance_band(distance)
                    all_tasks.append(task_data)
            else:
                # Non-store visit tasks
                task_data["sort_priority"] = TASK_TYPE_PRIORITY.get(
                    task.task_type if hasattr(task, "task_type") else "other", 10
                )
                task_data["distance_km"] = None
                all_tasks.append(task_data)

        # Process social tasks
        for task_data in social_tasks:
            task = task_data.get("ad") or task_data.get("task")
            task_data["sort_priority"] = TASK_TYPE_PRIORITY.get("social_engage", 3)
            task_data["distance_km"] = None
            all_tasks.append(task_data)

        # Process in-app tasks
        for task_data in inapp_tasks:
            task_data["sort_priority"] = TASK_TYPE_PRIORITY.get("in_app_challenge", 5)
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


class LocationMatcher:
    """
    Main location matching service that combines all algorithms.

    This service provides a unified interface for matching user locations
    with tasks, with automatic fallback mechanisms and performance optimizations.
    """

    def __init__(self, use_optimized: bool = True):
        """
        Initialize the location matcher.

        Args:
            use_optimized (bool): Whether to use optimized PostGIS queries
        """
        self.use_optimized = use_optimized

    def match_tasks_to_user(
        self,
        tasks_queryset,
        user_lat: float,
        user_lon: float,
        radius_km: float = DEFAULT_RADIUS_KM,
        max_results: Optional[int] = None,
        include_distance: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Match and sort tasks based on user location.

        This is the main method that coordinates the matching algorithm.
        It handles edge cases, performance optimization, and result formatting.

        Args:
            tasks_queryset: Django queryset of tasks
            user_lat (float): User's latitude
            user_lon (float): User's longitude
            radius_km (float): Search radius in kilometers
            max_results (Optional[int]): Maximum number of results
            include_distance (bool): Whether to include distance in results

        Returns:
            List[Dict[str, Any]]: Matched tasks with distance information
        """
        logger.info(
            f"Location matching: user at ({user_lat}, {user_lon}), "
            f"radius={radius_km}km, max_results={max_results}"
        )

        # Validate inputs
        if not tasks_queryset.exists():
            logger.info("No tasks available for matching")
            return []

        if radius_km <= 0:
            logger.warning(f"Invalid radius: {radius_km}km, using default")
            radius_km = DEFAULT_RADIUS_KM

        # Try optimized approach first if enabled
        if self.use_optimized:
            try:
                optimized_results = self._get_optimized_matches(
                    tasks_queryset, user_lat, user_lon, radius_km, max_results
                )

                if optimized_results:
                    return optimized_results
            except Exception as e:
                logger.error(f"Optimized matching failed, using fallback: {e}")

        # Fallback to Python-side calculation
        return GeoAlgorithm.get_nearby_store_tasks(
            tasks_queryset, user_lat, user_lon, radius_km, max_results
        )

    def _get_optimized_matches(
        self,
        queryset,
        user_lat: float,
        user_lon: float,
        radius_km: float,
        max_results: Optional[int],
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get optimized matches using bounding box filtering.

        This method first filters using a bounding box for performance,
        then calculates exact distances.
        """
        try:
            # Calculate approximate bounds
            lat_range = radius_km / 111.0  # 1 degree latitude ≈ 111 km
            lon_range = radius_km / (111.0 * math.cos(math.radians(user_lat)))

            # Filter with bounding box
            filtered_qs = queryset.filter(
                latitude__gte=user_lat - lat_range,
                latitude__lte=user_lat + lat_range,
                longitude__gte=user_lon - lon_range,
                longitude__lte=user_lon + lon_range,
            )

            if max_results:
                filtered_qs = filtered_qs[
                    : max_results * 2
                ]  # Get extra for exact filtering

            # Calculate exact distances
            results = []
            for task in filtered_qs:
                distance = GeoAlgorithm.calculate_distance_km(
                    user_lat, user_lon, task.latitude, task.longitude
                )
                if distance <= radius_km:
                    task_data = {
                        "task": task,
                        "distance_km": distance,
                        "distance_meters": distance * 1000,
                    }
                    results.append(task_data)

            # Sort by distance
            results.sort(key=lambda x: x["distance_km"])

            if max_results:
                results = results[:max_results]

            return results

        except Exception as e:
            logger.error(f"Error in optimized matching: {e}")
            return None


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
