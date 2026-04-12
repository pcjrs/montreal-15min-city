"""SQL query builders for the 15-minute city auditor."""

NEARBY_STOPS = """
SELECT * FROM (
  SELECT stop_id, stop_name, stop_lat, stop_lon, agency, wheelchair_boarding,
    (6371000 * ACOS(
      LEAST(1.0, COS(RADIANS({lat})) * COS(RADIANS(stop_lat)) *
      COS(RADIANS(stop_lon) - RADIANS({lon})) +
      SIN(RADIANS({lat})) * SIN(RADIANS(stop_lat)))
    )) AS distance_m
  FROM unified_transit_stops
  WHERE stop_lat BETWEEN {lat} - 0.008 AND {lat} + 0.008
    AND stop_lon BETWEEN {lon} - 0.012 AND {lon} + 0.012
) t WHERE distance_m <= {radius}
ORDER BY distance_m
"""

NEARBY_FACILITIES = """
SELECT * FROM (
  SELECT facility_name, category, facility_type, lat, lon,
    (6371000 * ACOS(
      LEAST(1.0, COS(RADIANS({lat})) * COS(RADIANS(lat)) *
      COS(RADIANS(lon) - RADIANS({lon})) +
      SIN(RADIANS({lat})) * SIN(RADIANS(lat)))
    )) AS distance_m
  FROM unified_facilities
  WHERE lat BETWEEN {lat} - 0.02 AND {lat} + 0.02
    AND lon BETWEEN {lon} - 0.03 AND {lon} + 0.03
) t WHERE distance_m <= {radius}
ORDER BY category, distance_m
"""

STOP_HEADWAYS = """
SELECT h.stop_id, h.agency, h.time_period, h.avg_headway_min, h.departures
FROM stop_headways h
WHERE h.stop_id IN ({stop_ids})
  AND h.time_period = '{period}'
"""

ALL_FACILITIES = """
SELECT facility_name, category, facility_type, lat, lon
FROM unified_facilities
WHERE lat BETWEEN 45.3 AND 45.75
  AND lon BETWEEN -74.0 AND -73.4
"""

ALL_STOPS_WITH_HEADWAY = """
SELECT s.stop_id, s.stop_name, s.stop_lat, s.stop_lon, s.agency, s.wheelchair_boarding,
  h.avg_headway_min, h.departures
FROM unified_transit_stops s
LEFT JOIN stop_headways h ON s.stop_id = h.stop_id AND s.agency = h.agency AND h.time_period = 'midday'
WHERE s.stop_lat BETWEEN 45.3 AND 45.75
  AND s.stop_lon BETWEEN -74.0 AND -73.4
"""

ALL_POPULATION = """
SELECT postal_code, fsa_name, borough, longitude, latitude, population, total_dwellings
FROM population_fsa
WHERE population > 0
ORDER BY borough, postal_code
"""

ROUTES_AT_STOP_STM = """
SELECT DISTINCT r.route_short_name, r.route_long_name, r.route_type
FROM transit_stm_stop_times st
JOIN transit_stm_trips t ON st.trip_id = t.trip_id
JOIN transit_stm_routes r ON t.route_id = r.route_id
WHERE CAST(st.stop_id AS STRING) = '{stop_id}'
LIMIT 20
"""

ROUTES_AT_STOP_STL = """
SELECT DISTINCT r.route_short_name, r.route_long_name, r.route_type
FROM transit_stl_stop_times st
JOIN transit_stl_trips t ON st.trip_id = t.trip_id
JOIN transit_stl_routes r ON t.route_id = r.route_id
WHERE st.stop_id = '{stop_id}'
LIMIT 20
"""

FACILITIES_BY_CATEGORY_IN_BOROUGH = """
SELECT f.category, f.facility_type, COUNT(*) as cnt
FROM unified_facilities f
WHERE f.lat BETWEEN {min_lat} AND {max_lat}
  AND f.lon BETWEEN {min_lon} AND {max_lon}
GROUP BY f.category, f.facility_type
ORDER BY f.category, cnt DESC
"""

BOROUGH_FSAS = """
SELECT postal_code, fsa_name, latitude, longitude, population
FROM population_fsa
WHERE UPPER(borough) = UPPER('{borough}')
ORDER BY postal_code
"""

DESERT_DETECTION = """
WITH fsa_stops AS (
  SELECT p.postal_code, p.borough, p.population, p.latitude, p.longitude,
    COUNT(DISTINCT s.stop_id) as stop_count,
    AVG(h.avg_headway_min) as avg_headway
  FROM population_fsa p
  LEFT JOIN unified_transit_stops s
    ON s.stop_lat BETWEEN p.latitude - 0.008 AND p.latitude + 0.008
    AND s.stop_lon BETWEEN p.longitude - 0.012 AND p.longitude + 0.012
  LEFT JOIN stop_headways h
    ON s.stop_id = h.stop_id AND s.agency = h.agency AND h.time_period = 'midday'
  WHERE p.population > 0
  GROUP BY p.postal_code, p.borough, p.population, p.latitude, p.longitude
),
fsa_facilities AS (
  SELECT p.postal_code,
    COUNT(DISTINCT CASE WHEN f.category = 'healthcare' THEN f.facility_name END) as healthcare_count,
    COUNT(DISTINCT CASE WHEN f.category = 'education' THEN f.facility_name END) as education_count,
    COUNT(DISTINCT CASE WHEN f.category = 'cultural' THEN f.facility_name END) as cultural_count,
    COUNT(DISTINCT CASE WHEN f.category = 'recreation' THEN f.facility_name END) as recreation_count
  FROM population_fsa p
  LEFT JOIN unified_facilities f
    ON f.lat BETWEEN p.latitude - 0.015 AND p.latitude + 0.015
    AND f.lon BETWEEN p.longitude - 0.02 AND p.longitude + 0.02
  WHERE p.population > 0
  GROUP BY p.postal_code
)
SELECT s.postal_code, s.borough, s.population, s.latitude, s.longitude,
  s.stop_count, ROUND(s.avg_headway, 1) as avg_headway,
  COALESCE(ff.healthcare_count, 0) as healthcare,
  COALESCE(ff.education_count, 0) as education,
  COALESCE(ff.cultural_count, 0) as cultural,
  COALESCE(ff.recreation_count, 0) as recreation,
  (CASE WHEN COALESCE(ff.healthcare_count, 0) > 0 THEN 1 ELSE 0 END +
   CASE WHEN COALESCE(ff.education_count, 0) > 0 THEN 1 ELSE 0 END +
   CASE WHEN COALESCE(ff.cultural_count, 0) > 0 THEN 1 ELSE 0 END +
   CASE WHEN COALESCE(ff.recreation_count, 0) > 0 THEN 1 ELSE 0 END) as score
FROM fsa_stops s
LEFT JOIN fsa_facilities ff ON s.postal_code = ff.postal_code
ORDER BY score ASC, s.population DESC
"""
