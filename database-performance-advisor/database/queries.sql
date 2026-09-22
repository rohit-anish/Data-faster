-- Useful queries for database analysis and performance monitoring

-- Find slow queries
SELECT 
    query,
    AVG(execution_time_ms) as avg_time,
    MAX(execution_time_ms) as max_time,
    COUNT(*) as execution_count
FROM performance_metrics
GROUP BY query
ORDER BY avg_time DESC
LIMIT 20;

-- Get recent analysis results
SELECT 
    id,
    query,
    analysis_result,
    recommendations,
    created_at
FROM query_analysis
ORDER BY created_at DESC
LIMIT 50;

-- View all index recommendations
SELECT 
    table_name,
    column_names,
    recommendation,
    priority,
    created_at
FROM index_recommendations
ORDER BY priority DESC, created_at DESC;

-- Performance metrics by database
SELECT 
    database_name,
    COUNT(*) as query_count,
    AVG(execution_time_ms) as avg_execution_time,
    MAX(execution_time_ms) as max_execution_time,
    MIN(execution_time_ms) as min_execution_time
FROM performance_metrics
GROUP BY database_name;
