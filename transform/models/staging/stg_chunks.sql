select
    chunk_id,
    doc_id,
    doc_type,
    title,
    cast(doc_date as date) as doc_date,
    url,
    section,
    chunk_text
from {{ source('tidy', 'chunks') }}
