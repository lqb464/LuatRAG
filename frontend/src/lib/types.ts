export type CorpusSource = {
  id: string;
  ownerId?: string;
  name: string;
  kind: string;
  mimeType: string;
  byteSize: number;
  status: 'ready' | 'processing' | 'error';
  chunkCount: number;
  sourceUrl?: string | null;
  legalType?: string | null;
  legalArea?: string | null;
  documentNumber?: string | null;
  issuingAuthority?: string | null;
  issueDate?: string | null;
  effectiveStatus?: string | null;
  sourceContentHash?: string | null;
  bodySource?: string | null;
  selectionGroup?: string | null;
  builtin?: boolean;
  createdAt: string;
};

export type ExtractedSegment = {
  locator: string;
  heading?: string;
  text: string;
};

export type CorpusChunk = {
  id: string;
  sourceId: string;
  sourceName: string;
  sourceUrl?: string | null;
  locator: string;
  heading?: string | null;
  text: string;
  legalType?: string | null;
  documentNumber?: string | null;
  issuingAuthority?: string | null;
  issueDate?: string | null;
  effectiveStatus?: string | null;
  score?: number;
  builtin?: boolean;
};

export type RagClaim = {
  text: string;
  sourceIds: string[];
};

export type RagAnswer = {
  id: string;
  question: string;
  summary: string;
  answer: string;
  claims: RagClaim[];
  limitations: string[];
  suggestedQuestions: string[];
  insufficientContext: boolean;
  model: string;
  durationMs: number;
  evidence: CorpusChunk[];
  conversationId?: string;
};
