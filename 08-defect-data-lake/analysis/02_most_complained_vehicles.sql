-- Which vehicles draw the most complaints? Make, model and model year, received in {year}
SELECT make, model, model_year,
       count(*)                                         AS complaints,
       round(100.0 * count_if(crash) / count(*), 1)     AS crash_pct,
       arbitrary(component_group)                       AS example_component
FROM {database}.complaints_elt
WHERE received_year = {year} AND product_type = 'V' AND model_year IS NOT NULL
GROUP BY make, model, model_year
ORDER BY complaints DESC
LIMIT 10
