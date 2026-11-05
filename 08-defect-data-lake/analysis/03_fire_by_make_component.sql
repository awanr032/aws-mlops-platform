-- Fire-related complaints: which makes and systems? (all years in the lake)
SELECT make, component_group, count(*) AS fire_complaints
FROM {database}.complaints_elt
WHERE fire AND make IS NOT NULL
GROUP BY make, component_group
ORDER BY fire_complaints DESC
LIMIT 10
