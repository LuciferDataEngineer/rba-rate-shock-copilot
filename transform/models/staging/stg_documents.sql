select
    doc_id,
    doc_type,
    title,
    cast(doc_date as date) as doc_date,
    url,
    cast(n_chars as integer) as n_chars
from {{ source('tidy', 'documents') }}
