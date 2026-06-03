export interface ChunkMetadata {
  company_name?: string | null;
  ticker?: string | null;
  filing_type?: string | null;
  filing_year?: string | null;
  section_name?: string | null;
  page_number?: number | null;
  source_document?: string | null;
}

export interface SourceCitation {
  chunk_id: string;
  ticker: string;
  excerpt: string;
  score?: number;
  form_type?: string;
  source_url?: string;
  section_name?: string;
  company_name?: string | null;
  filing_type?: string | null;
  filing_year?: string | null;
  page_number?: number | null;
  source_document?: string | null;
  metadata?: ChunkMetadata | null;
  title?: string | null;
}

export interface UserAnswer {
  answer: string;
  key_details: string[];
  relevant_metrics: string[];
  sources: string[];
  confidence: string;
  confidence_percent?: number;
  confidence_display?: string;
  text: string;
}

export interface RetrievedChunkDebug {
  chunk_id: string;
  ticker?: string | null;
  section_name?: string | null;
  relevance_score?: number | null;
}

export interface DebugInfo {
  detected_companies?: { ticker: string; company_name: string }[];
  detected_domain?: string | null;
  domain_relevance_score?: number | null;
  retrieval_skipped?: boolean;
  retrieval_skip_reason?: string | null;
  applied_filters?: Record<string, unknown>;
  retrieved_chunks?: RetrievedChunkDebug[];
  relevance_scores?: number[];
  groundedness_score?: number | null;
  citation_coverage?: number | null;
  hallucination_risk?: number | null;
  has_unmarked_inference?: boolean | null;
  validation_notes?: string;
  company_coverage?: {
    ticker: string;
    display_name: string;
    status: string;
  }[];
  route?: string;
  confidence_score?: number;
  response_mode?: string;
  evaluation_notes?: string | null;
  additional_sources?: string[];
  confidence_display?: string | null;
  confidence_percent?: number | null;
}

export interface ChatResponse {
  user_answer: UserAnswer;
  debug_info: DebugInfo;
  sources: SourceCitation[];
  answer?: string;
  answer_body?: string;
  confidence?: number;
  route?: string;
}

export interface DocumentStats {
  documents: number;
  chunks: number;
  db_ok?: boolean;
  hint?: string;
}
