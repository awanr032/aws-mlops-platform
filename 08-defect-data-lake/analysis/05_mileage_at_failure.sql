-- At what mileage do systems fail? Median and 90th percentile, model years {year}-5 to {year}
SELECT component_group,
       count(*)                                   AS complaints_with_mileage,
       approx_percentile(miles, 0.5)              AS median_miles,
       approx_percentile(miles, 0.9)              AS p90_miles
FROM {database}.complaints_elt
WHERE model_year BETWEEN {year} - 5 AND {year} AND miles > 0
GROUP BY component_group
HAVING count(*) >= 200
ORDER BY median_miles DESC
LIMIT 10
