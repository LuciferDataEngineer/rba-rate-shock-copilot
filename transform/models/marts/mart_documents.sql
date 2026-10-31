select
    doc_id,
    doc_type,
    title,
    doc_date,
    url,
    n_chars
from {{ ref('stg_documents') }}
