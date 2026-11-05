-- Which systems fail most? Top component groups for complaints received in {year}
SELECT component_group,
       count(*)                       AS complaints,
       count_if(crash)                AS crashes,
       count_if(fire)                 AS fires,
       sum(injured)                   AS injured
FROM {database}.complaints_elt
WHERE received_year = {year}
GROUP BY component_group
ORDER BY complaints DESC
LIMIT 10
