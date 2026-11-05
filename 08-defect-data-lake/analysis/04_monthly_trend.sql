-- Complaints per month (all years in the lake): is the volume changing?
SELECT date_trunc('month', received_date) AS month,
       count(*)                           AS complaints,
       count_if(crash)                    AS crashes
FROM {database}.complaints_elt
GROUP BY 1
ORDER BY 1 DESC
LIMIT 24
