'use client';

import * as React from 'react';
import {
  Archive,
  ArrowUp,
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  Clock3,
  Copy,
  Database,
  Download,
  ExternalLink,
  File,
  FileSearch,
  FileSpreadsheet,
  FileText,
  Gauge,
  History,
  Info,
  LoaderCircle,
  Menu,
  MoreHorizontal,
  PanelRight,
  Plus,
  RefreshCw,
  Scale,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
} from 'lucide-react';

import type { CorpusChunk, CorpusSource, RagAnswer } from '@/lib/types';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { Toaster, toast } from '@/components/ui/toast';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

type ApiError = {
  error?: { code?: string; message?: string; retryable?: boolean };
};
type CorpusManifest = {
  dataset: string;
  creator: string;
  revision: string;
  source: string;
  upstream: string;
  license: string;
  licenseUrl: string;
  snapshotDate: string;
  contentOrigin: string;
  note: string;
};
type Health = {
  status: string;
  user?: { email: string | null };
  generation?: { configured: boolean; model: string };
};
type UiMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  answer?: RagAnswer;
};
type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};
type ModelContextLike = {
  registerTool: (
    tool: {
      name: string;
      title: string;
      description: string;
      inputSchema: object;
      annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
      execute: (input: unknown) => unknown;
    },
    options?: { signal?: AbortSignal },
  ) => void | Promise<void>;
};

const SAMPLE_QUESTIONS = [
  'Điều 113 Bộ luật Lao động 45/2019/QH14 quy định nghỉ hằng năm ra sao?',
  'Nghị định 13/2023/NĐ-CP quy định quyền của chủ thể dữ liệu như thế nào?',
  'Luật Giao dịch điện tử 20/2023/QH15 quy định giá trị pháp lý của thông điệp dữ liệu ra sao?',
];

const kindIcon: Record<string, React.ComponentType<{ size?: number }>> = {
  pdf: FileText,
  document: FileText,
  slides: File,
  sheet: FileSpreadsheet,
  text: FileText,
  'legal-document': Scale,
};

async function api<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, init);
  const payload = (await response.json().catch(() => ({}))) as T & ApiError;
  if (!response.ok) {
    throw new Error(payload.error?.message || 'Không thể hoàn tất yêu cầu.');
  }
  return payload;
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function SourceRow({
  source,
  active,
  onSelect,
  onDelete,
  onReindex,
}: {
  source: CorpusSource;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onReindex: () => void;
}) {
  const Icon = kindIcon[source.kind] || FileText;
  return (
    <div className={`legal-source-row ${active ? 'is-active' : ''}`}>
      <button className="legal-source-main" onClick={onSelect} type="button">
        <span className="legal-file-icon">
          <Icon size={16} />
        </span>
        <span className="legal-source-copy">
          <strong>{source.name}</strong>
          <small>
            {source.builtin ? 'VBPL · ' : `${formatBytes(source.byteSize)} · `}
            {source.chunkCount} đoạn
          </small>
        </span>
      </button>
      {!source.builtin && (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Tùy chọn ${source.name}`}
              />
            }
          >
            <MoreHorizontal size={16} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onReindex}>
              <RefreshCw /> Lập chỉ mục lại
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onClick={onDelete}>
              <Trash2 /> Xóa nguồn
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}

function SourcesPanel({
  sources,
  selectedId,
  loading,
  onSelect,
  onUpload,
  onDelete,
  onReindex,
}: {
  sources: CorpusSource[];
  selectedId?: string;
  loading: boolean;
  onSelect: (source: CorpusSource) => void;
  onUpload: () => void;
  onDelete: (source: CorpusSource) => void;
  onReindex: (source: CorpusSource) => void;
}) {
  const [query, setQuery] = React.useState('');
  const normalized = query.toLocaleLowerCase('vi');
  const filtered = sources.filter((source) =>
    source.name.toLocaleLowerCase('vi').includes(normalized),
  );
  const builtin = filtered.filter((source) => source.builtin);
  const uploaded = filtered.filter((source) => !source.builtin);
  return (
    <div className="legal-panel-inner">
      <div className="legal-panel-heading">
        <div>
          <span className="eyebrow">Kho căn cứ</span>
          <h2>Nguồn pháp luật</h2>
        </div>
        <Button size="sm" onClick={onUpload}>
          <Plus /> Thêm
        </Button>
      </div>
      <div className="legal-search">
        <Search size={15} />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Tìm số hiệu, tiêu đề…"
          aria-label="Tìm nguồn"
        />
      </div>
      <div className="legal-source-summary">
        <Database size={14} />
        <span>
          {sources.length} văn bản ·{' '}
          {sources.reduce((sum, item) => sum + item.chunkCount, 0)} đoạn
        </span>
      </div>
      <ScrollArea className="legal-source-scroll">
        {loading ? (
          <div className="legal-loading">
            <LoaderCircle className="spin" /> Đang tải kho dữ liệu…
          </div>
        ) : (
          <>
            <div className="legal-group-label">
              Corpus VBPL <Badge variant="secondary">{builtin.length}</Badge>
            </div>
            {builtin.map((source) => (
              <SourceRow
                key={source.id}
                source={source}
                active={source.id === selectedId}
                onSelect={() => onSelect(source)}
                onDelete={() => onDelete(source)}
                onReindex={() => onReindex(source)}
              />
            ))}
            <div className="legal-group-label">
              Tài liệu của bạn{' '}
              <Badge variant="secondary">{uploaded.length}</Badge>
            </div>
            {uploaded.length ? (
              uploaded.map((source) => (
                <SourceRow
                  key={source.id}
                  source={source}
                  active={source.id === selectedId}
                  onSelect={() => onSelect(source)}
                  onDelete={() => onDelete(source)}
                  onReindex={() => onReindex(source)}
                />
              ))
            ) : (
              <button
                type="button"
                className="legal-empty-upload"
                onClick={onUpload}
              >
                <UploadCloud size={18} /> Tải tài liệu nội bộ để hỏi cùng corpus
              </button>
            )}
          </>
        )}
      </ScrollArea>
    </div>
  );
}

function EvidencePanel({
  evidence,
  selected,
  onSelect,
}: {
  evidence: CorpusChunk[];
  selected?: CorpusChunk;
  onSelect: (chunk: CorpusChunk) => void;
}) {
  const current = selected || evidence[0];
  return (
    <div className="legal-panel-inner evidence-inner">
      <div className="legal-panel-heading">
        <div>
          <span className="eyebrow">Kiểm chứng</span>
          <h2>Căn cứ truy hồi</h2>
        </div>
        <Badge variant="outline">{evidence.length}</Badge>
      </div>
      {current ? (
        <ScrollArea className="legal-evidence-scroll">
          <div className="legal-evidence-hero">
            <div className="evidence-kicker">
              <ShieldCheck size={14} /> Đoạn được chọn
            </div>
            <h3>{current.sourceName}</h3>
            <div className="evidence-meta">
              <span>{current.locator}</span>
              {typeof current.score === 'number' && (
                <span>Điểm {current.score.toFixed(2)}</span>
              )}
            </div>
            <blockquote>{current.text}</blockquote>
            {current.sourceUrl && (
              <a href={current.sourceUrl} target="_blank" rel="noreferrer">
                Mở văn bản gốc <ExternalLink size={13} />
              </a>
            )}
          </div>
          {evidence.length > 1 && (
            <div className="legal-evidence-list">
              <span className="eyebrow">Các đoạn liên quan</span>
              {evidence.map((chunk, index) => (
                <button
                  type="button"
                  key={chunk.id}
                  className={`legal-evidence-item ${chunk.id === current.id ? 'is-active' : ''}`}
                  onClick={() => onSelect(chunk)}
                >
                  <span>{index + 1}</span>
                  <div>
                    <strong>{chunk.heading || chunk.locator}</strong>
                    <small>{chunk.sourceName}</small>
                  </div>
                </button>
              ))}
            </div>
          )}
        </ScrollArea>
      ) : (
        <div className="legal-empty-evidence">
          <FileSearch size={28} />
          <h3>Chưa có căn cứ</h3>
          <p>Đặt câu hỏi hoặc chọn một nguồn để xem các đoạn đã lập chỉ mục.</p>
        </div>
      )}
    </div>
  );
}

function AnswerView({
  answer,
  onEvidence,
  onSuggest,
}: {
  answer: RagAnswer;
  onEvidence: (chunk: CorpusChunk) => void;
  onSuggest: (question: string) => void;
}) {
  const evidenceById = new Map(
    answer.evidence.map((chunk) => [chunk.id, chunk]),
  );
  return (
    <div
      className={`legal-answer ${answer.insufficientContext ? 'is-limited' : ''}`}
    >
      <div className="legal-answer-top">
        <span className="assistant-mark">
          <Scale size={16} />
        </span>
        <div>
          <span>LuatRAG</span>
          <small>
            {answer.model === 'not-called'
              ? 'Không gọi LLM'
              : 'Gemini chỉ tổng hợp'}{' '}
            · {answer.durationMs} ms
          </small>
        </div>
      </div>
      <h3>{answer.summary}</h3>
      <p className="legal-answer-body">{answer.answer}</p>
      {answer.claims.length > 0 && (
        <div className="legal-claims">
          {answer.claims.map((claim, index) => (
            <div className="legal-claim" key={`${answer.id}-${index}`}>
              <div className="claim-number">
                {String(index + 1).padStart(2, '0')}
              </div>
              <div>
                <p>{claim.text}</p>
                <div className="claim-citations">
                  {claim.sourceIds.map((id) => {
                    const chunk = evidenceById.get(id);
                    if (!chunk) return null;
                    const evidenceIndex =
                      answer.evidence.findIndex((item) => item.id === id) + 1;
                    return (
                      <button
                        type="button"
                        key={id}
                        onClick={() => onEvidence(chunk)}
                      >
                        [{evidenceIndex}] {chunk.locator}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {answer.limitations.length > 0 && (
        <div className="legal-limitations">
          <Info size={15} />
          <div>
            {answer.limitations.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
        </div>
      )}
      {answer.suggestedQuestions.length > 0 && (
        <div className="legal-answer-suggestions">
          {answer.suggestedQuestions.map((question) => (
            <button
              type="button"
              onClick={() => onSuggest(question)}
              key={question}
            >
              {question}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function toMarkdown(answer: RagAnswer): string {
  const evidenceById = new Map(
    answer.evidence.map((chunk) => [chunk.id, chunk]),
  );
  return [
    '# LuatRAG — Phiếu tra cứu',
    '',
    `**Câu hỏi:** ${answer.question}`,
    '',
    `## ${answer.summary}`,
    '',
    answer.answer,
    '',
    ...answer.claims.flatMap((claim, index) => [
      `${index + 1}. ${claim.text} ${claim.sourceIds.map((id) => `[${answer.evidence.findIndex((item) => item.id === id) + 1}]`).join(' ')}`,
      '',
    ]),
    '## Căn cứ',
    '',
    ...answer.evidence.map(
      (chunk, index) =>
        `${index + 1}. ${chunk.sourceName} — ${chunk.locator}${evidenceById.has(chunk.id) && chunk.sourceUrl ? ` — ${chunk.sourceUrl}` : ''}`,
    ),
    '',
    '## Giới hạn',
    '',
    ...answer.limitations.map((item) => `- ${item}`),
    '',
    '_Thông tin dùng để tra cứu, không thay thế tư vấn pháp lý._',
  ].join('\n');
}

export function LuatRagWorkspace() {
  const [sources, setSources] = React.useState<CorpusSource[]>([]);
  const [corpus, setCorpus] = React.useState<CorpusManifest>();
  const [health, setHealth] = React.useState<Health>();
  const [messages, setMessages] = React.useState<UiMessage[]>([]);
  const [conversations, setConversations] = React.useState<
    ConversationSummary[]
  >([]);
  const [conversationId, setConversationId] = React.useState<string>();
  const [question, setQuestion] = React.useState('');
  const [mode, setMode] = React.useState<'fast' | 'deep'>('fast');
  const [asking, setAsking] = React.useState(false);
  const [sourcesLoading, setSourcesLoading] = React.useState(true);
  const [selectedSourceId, setSelectedSourceId] = React.useState<string>();
  const [evidence, setEvidence] = React.useState<CorpusChunk[]>([]);
  const [selectedEvidence, setSelectedEvidence] = React.useState<CorpusChunk>();
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [uploadProgress, setUploadProgress] = React.useState(0);
  const [uploadStage, setUploadStage] = React.useState('Chọn tệp để bắt đầu');
  const [uploadBusy, setUploadBusy] = React.useState(false);
  const [deleteTarget, setDeleteTarget] = React.useState<CorpusSource>();
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [infoOpen, setInfoOpen] = React.useState(false);
  const [sourcesSheet, setSourcesSheet] = React.useState(false);
  const [evidenceSheet, setEvidenceSheet] = React.useState(false);
  const [dragging, setDragging] = React.useState(false);
  const fileInput = React.useRef<HTMLInputElement>(null);
  const endRef = React.useRef<HTMLDivElement>(null);
  const askRef = React.useRef<
    (value: string) => Promise<RagAnswer | undefined>
  >(async () => undefined);
  const sourcesRef = React.useRef(sources);

  const loadSources = React.useCallback(async () => {
    await Promise.resolve();
    setSourcesLoading(true);
    try {
      const result = await api<{
        sources: CorpusSource[];
        corpus: CorpusManifest;
      }>('/api/sources');
      setSources(result.sources);
      setCorpus(result.corpus);
      setSelectedSourceId((current) => current || result.sources[0]?.id);
    } catch (error) {
      toast.add({
        title: 'Không tải được kho dữ liệu',
        description: error instanceof Error ? error.message : undefined,
        type: 'error',
      });
    } finally {
      setSourcesLoading(false);
    }
  }, []);

  const loadConversations = React.useCallback(async () => {
    try {
      const result = await api<{ conversations: ConversationSummary[] }>(
        '/api/conversations',
      );
      setConversations(result.conversations);
    } catch {
      /* Health banner already communicates backend availability. */
    }
  }, []);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void Promise.all([
        loadSources(),
        loadConversations(),
        api<Health>('/api/health')
          .then(setHealth)
          .catch(() => setHealth({ status: 'error' })),
      ]);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadConversations, loadSources]);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, asking]);

  const selectSource = React.useCallback(async (source: CorpusSource) => {
    setSelectedSourceId(source.id);
    setSourcesSheet(false);
    try {
      const result = await api<{ evidence: CorpusChunk[] }>(
        `/api/sources/${encodeURIComponent(source.id)}`,
      );
      setEvidence(result.evidence);
      setSelectedEvidence(result.evidence[0]);
    } catch (error) {
      toast.add({
        title: 'Không mở được nguồn',
        description: error instanceof Error ? error.message : undefined,
        type: 'error',
      });
    }
  }, []);

  const submitQuestion = React.useCallback(
    async (raw: string) => {
      const clean = raw.trim();
      if (clean.length < 4 || asking) return undefined;
      const userMessage: UiMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: clean,
      };
      setMessages((current) => [...current, userMessage]);
      setQuestion('');
      setAsking(true);
      try {
        const result = await api<{ answer: RagAnswer }>('/api/ask', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ question: clean, conversationId, mode }),
        });
        setMessages((current) => [
          ...current,
          {
            id: result.answer.id,
            role: 'assistant',
            content: result.answer.summary,
            answer: result.answer,
          },
        ]);
        setConversationId(result.answer.conversationId);
        setEvidence(result.answer.evidence);
        setSelectedEvidence(result.answer.evidence[0]);
        void loadConversations();
        return result.answer;
      } catch (error) {
        toast.add({
          title: 'Chưa thể trả lời',
          description: error instanceof Error ? error.message : undefined,
          type: 'error',
        });
        setMessages((current) =>
          current.filter((message) => message.id !== userMessage.id),
        );
        return undefined;
      } finally {
        setAsking(false);
      }
    },
    [asking, conversationId, loadConversations, mode],
  );

  React.useEffect(() => {
    sourcesRef.current = sources;
  }, [sources]);

  React.useEffect(() => {
    askRef.current = submitQuestion;
  }, [submitQuestion]);

  React.useEffect(() => {
    const context = (document as Document & { modelContext?: ModelContextLike })
      .modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const register = async () => {
      await context.registerTool(
        {
          name: 'ask_luatrag',
          title: 'Hỏi LuatRAG',
          description:
            'Tra cứu kho pháp luật hiện có bằng retrieval CPU-first và nhận câu trả lời có căn cứ.',
          inputSchema: {
            type: 'object',
            properties: {
              question: { type: 'string', minLength: 4, maxLength: 1200 },
            },
            required: ['question'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: true },
          execute: async (input) => {
            const value = input as { question?: unknown };
            if (typeof value.question !== 'string')
              throw new Error('question must be a string');
            const answer = await askRef.current(value.question);
            if (!answer) throw new Error('LuatRAG could not answer');
            return {
              summary: answer.summary,
              insufficientContext: answer.insufficientContext,
              citations: answer.claims.flatMap((claim) => claim.sourceIds)
                .length,
            };
          },
        },
        { signal: lifecycle.signal },
      );
      await context.registerTool(
        {
          name: 'list_legal_sources',
          title: 'Liệt kê nguồn LuatRAG',
          description:
            'Liệt kê nguồn pháp luật và tài liệu người dùng đang có trong workspace.',
          inputSchema: {
            type: 'object',
            properties: {},
            additionalProperties: false,
          },
          annotations: { readOnlyHint: true, untrustedContentHint: true },
          execute: () => ({
            sources: sourcesRef.current.map((source) => ({
              id: source.id,
              name: source.name,
              chunks: source.chunkCount,
              builtin: Boolean(source.builtin),
            })),
          }),
        },
        { signal: lifecycle.signal },
      );
    };
    void register().catch(() => undefined);
    return () => lifecycle.abort();
  }, []);

  const handleFile = React.useCallback(
    async (file: File) => {
      setUploadBusy(true);
      setUploadProgress(12);
      setUploadStage('Đang gửi tài liệu tới máy chủ…');
      try {
        const form = new FormData();
        form.set('file', file);
        setUploadProgress(40);
        setUploadStage('Máy chủ đang trích xuất và lập chỉ mục…');
        const result = await api<{ source: CorpusSource }>('/api/sources', {
          method: 'POST',
          body: form,
        });
        setUploadProgress(100);
        setUploadStage(
          `Hoàn tất ${result.source.chunkCount} đoạn có thể truy hồi.`,
        );
        await loadSources();
        toast.add({
          title: 'Đã thêm nguồn',
          description: `${result.source.name} · ${result.source.chunkCount} đoạn`,
          type: 'success',
        });
        window.setTimeout(() => {
          setUploadOpen(false);
          setUploadProgress(0);
          setUploadStage('Chọn tệp để bắt đầu');
        }, 800);
      } catch (error) {
        setUploadProgress(0);
        setUploadStage(
          error instanceof Error ? error.message : 'Không thể xử lý tệp.',
        );
        toast.add({
          title: 'Tải lên thất bại',
          description: error instanceof Error ? error.message : undefined,
          type: 'error',
        });
      } finally {
        setUploadBusy(false);
      }
    },
    [loadSources],
  );

  const reindex = React.useCallback(
    async (source: CorpusSource) => {
      try {
        const result = await api<{ chunkCount: number }>(
          `/api/sources/${encodeURIComponent(source.id)}/reindex`,
          { method: 'POST' },
        );
        await loadSources();
        toast.add({
          title: 'Đã lập chỉ mục lại',
          description: `${result.chunkCount} đoạn sẵn sàng`,
          type: 'success',
        });
      } catch (error) {
        toast.add({
          title: 'Không thể lập chỉ mục',
          description: error instanceof Error ? error.message : undefined,
          type: 'error',
        });
      }
    },
    [loadSources],
  );

  const confirmDelete = React.useCallback(async () => {
    if (!deleteTarget) return;
    try {
      const activeConversationUsesSource = messages.some((message) =>
        message.answer?.evidence.some(
          (chunk) => chunk.sourceId === deleteTarget.id,
        ),
      );
      await api(`/api/sources/${encodeURIComponent(deleteTarget.id)}`, {
        method: 'DELETE',
      });
      if (selectedSourceId === deleteTarget.id) {
        setEvidence([]);
        setSelectedEvidence(undefined);
        setSelectedSourceId(undefined);
      }
      if (activeConversationUsesSource) {
        setMessages([]);
        setConversationId(undefined);
      }
      setDeleteTarget(undefined);
      await Promise.all([loadSources(), loadConversations()]);
      toast.add({
        title: 'Đã xóa nguồn, tệp và lịch sử liên quan',
        type: 'success',
      });
    } catch (error) {
      toast.add({
        title: 'Không thể xóa nguồn',
        description: error instanceof Error ? error.message : undefined,
        type: 'error',
      });
    }
  }, [
    deleteTarget,
    loadConversations,
    loadSources,
    messages,
    selectedSourceId,
  ]);

  const loadConversation = React.useCallback(async (id: string) => {
    try {
      const result = await api<{
        messages: Array<{
          id: string;
          role: 'user' | 'assistant';
          content: string;
          evidence_json: string | null;
        }>;
      }>(`/api/conversations/${encodeURIComponent(id)}`);
      let previousQuestion = '';
      const restored: UiMessage[] = [];
      for (const message of result.messages) {
        if (message.role === 'user') {
          previousQuestion = message.content;
          restored.push({
            id: message.id,
            role: 'user',
            content: message.content,
          });
          continue;
        }
        try {
          const saved = JSON.parse(message.content) as Omit<
            RagAnswer,
            'id' | 'question' | 'evidence'
          >;
          const savedEvidence = message.evidence_json
            ? (JSON.parse(message.evidence_json) as CorpusChunk[])
            : [];
          const answer: RagAnswer = {
            ...saved,
            id: message.id,
            question: previousQuestion,
            evidence: savedEvidence,
            conversationId: id,
          };
          restored.push({
            id: message.id,
            role: 'assistant',
            content: answer.summary,
            answer,
          });
        } catch {
          /* Ignore a single corrupt history row. */
        }
      }
      setConversationId(id);
      setMessages(restored);
      setHistoryOpen(false);
      const latest = [...restored]
        .reverse()
        .find((message) => message.answer)?.answer;
      if (latest) {
        setEvidence(latest.evidence);
        setSelectedEvidence(latest.evidence[0]);
      }
    } catch (error) {
      toast.add({
        title: 'Không mở được lịch sử',
        description: error instanceof Error ? error.message : undefined,
        type: 'error',
      });
    }
  }, []);

  const latestAnswer = [...messages]
    .reverse()
    .find((message) => message.answer)?.answer;
  const exportLatest = () => {
    if (!latestAnswer) return;
    const blob = new Blob([toMarkdown(latestAnswer)], {
      type: 'text/markdown;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `luatrag-${Date.now()}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const copyLatest = async () => {
    if (!latestAnswer) return;
    await navigator.clipboard.writeText(toMarkdown(latestAnswer));
    toast.add({ title: 'Đã sao chép phiếu tra cứu', type: 'success' });
  };

  const panelSources = (
    <SourcesPanel
      sources={sources}
      selectedId={selectedSourceId}
      loading={sourcesLoading}
      onSelect={selectSource}
      onUpload={() => setUploadOpen(true)}
      onDelete={setDeleteTarget}
      onReindex={(source) => void reindex(source)}
    />
  );
  const panelEvidence = (
    <EvidencePanel
      evidence={evidence}
      selected={selectedEvidence}
      onSelect={(chunk) => {
        setSelectedEvidence(chunk);
        setEvidenceSheet(true);
      }}
    />
  );

  return (
    <TooltipProvider>
      <Toaster>
        <a className="skip-link" href="#legal-chat">
          Đi đến vùng hỏi đáp
        </a>
        <div className="legal-app">
          <header className="legal-header">
            <div className="legal-brand">
              <div className="legal-brand-mark">
                <Scale size={19} />
              </div>
              <div>
                <strong>LuatRAG</strong>
                <span>Vietnamese legal intelligence</span>
              </div>
            </div>
            <div className="legal-pipeline">
              <span>
                <Gauge size={14} /> CPU · parse + BM25
              </span>
              <i />
              <span>
                <Sparkles size={14} /> Gemini · chỉ sinh câu trả lời
              </span>
            </div>
            <div className="legal-header-actions">
              <Badge
                variant={
                  health?.status === 'ok' && health.generation?.configured
                    ? 'default'
                    : 'secondary'
                }
                className="legal-status"
              >
                <span className="status-dot" />
                {health?.status === 'ok'
                  ? health.generation?.configured
                    ? 'Sẵn sàng'
                    : 'Thiếu Gemini key'
                  : 'Đang kết nối'}
              </Badge>
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => setHistoryOpen(true)}
                      aria-label="Lịch sử"
                    />
                  }
                >
                  <History />
                </TooltipTrigger>
                <TooltipContent>Lịch sử tra cứu</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => setInfoOpen(true)}
                      aria-label="Thông tin hệ thống"
                    />
                  }
                >
                  <Info />
                </TooltipTrigger>
                <TooltipContent>Corpus và quyền riêng tư</TooltipContent>
              </Tooltip>
              <Button
                variant="outline"
                size="sm"
                className="mobile-source-button"
                onClick={() => setSourcesSheet(true)}
              >
                <Menu /> Nguồn
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="mobile-evidence-button"
                onClick={() => setEvidenceSheet(true)}
              >
                <PanelRight /> Căn cứ
              </Button>
            </div>
          </header>

          <div className="legal-workspace">
            <aside className="legal-left-panel">{panelSources}</aside>
            <main id="legal-chat" className="legal-chat" tabIndex={-1}>
              <div className="legal-chat-toolbar">
                <div>
                  <span className="eyebrow">Workspace riêng tư</span>
                  <h1>Tra cứu có căn cứ</h1>
                </div>
                <div className="legal-chat-actions">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={!latestAnswer}
                    onClick={() => void copyLatest()}
                  >
                    <Copy /> Sao chép
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={!latestAnswer}
                    onClick={exportLatest}
                  >
                    <Download /> Xuất phiếu
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setMessages([]);
                      setConversationId(undefined);
                      setEvidence([]);
                      setSelectedEvidence(undefined);
                    }}
                  >
                    <Plus /> Cuộc trao đổi mới
                  </Button>
                </div>
              </div>
              <ScrollArea className="legal-messages">
                <div className="legal-message-column">
                  {messages.length === 0 && (
                    <div className="legal-welcome">
                      <div className="welcome-seal">
                        <BookOpen size={25} />
                      </div>
                      <span className="eyebrow">
                        Bắt đầu từ văn bản, không từ suy đoán
                      </span>
                      <h2>Bạn cần kiểm tra quy định nào?</h2>
                      <p>
                        LuatRAG tìm đoạn liên quan bằng thuật toán cục bộ, sau
                        đó chỉ giao cho Gemini việc diễn đạt câu trả lời từ các
                        đoạn đó.
                      </p>
                      <div className="legal-starter-grid">
                        {SAMPLE_QUESTIONS.map((item, index) => (
                          <button
                            type="button"
                            key={item}
                            onClick={() => void submitQuestion(item)}
                          >
                            <span>0{index + 1}</span>
                            {item}
                            <ArrowUp size={15} />
                          </button>
                        ))}
                      </div>
                      <div className="legal-trust-row">
                        <span>
                          <ShieldCheck /> Có trích dẫn
                        </span>
                        <span>
                          <Database /> Dữ liệu bền vững
                        </span>
                        <span>
                          <Bot /> Không dùng Gemini để tìm nguồn
                        </span>
                      </div>
                    </div>
                  )}
                  {messages.map((message) =>
                    message.role === 'user' ? (
                      <div className="legal-user-message" key={message.id}>
                        <span>Bạn</span>
                        <p>{message.content}</p>
                      </div>
                    ) : message.answer ? (
                      <AnswerView
                        key={message.id}
                        answer={message.answer}
                        onEvidence={(chunk) => {
                          setSelectedEvidence(chunk);
                          setEvidenceSheet(true);
                        }}
                        onSuggest={(value) => void submitQuestion(value)}
                      />
                    ) : null,
                  )}
                  {asking && (
                    <div className="legal-thinking">
                      <span className="assistant-mark">
                        <Scale size={16} />
                      </span>
                      <div>
                        <strong>Đang tìm căn cứ</strong>
                        <p>
                          FTS5/BM25 đang xếp hạng đoạn; Gemini chưa được gọi cho
                          đến khi đủ bằng chứng.
                        </p>
                        <Progress value={62} />
                      </div>
                    </div>
                  )}
                  <div ref={endRef} />
                </div>
              </ScrollArea>
              <div className="legal-composer-wrap">
                <div className="legal-composer">
                  <Textarea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (
                        event.key === 'Enter' &&
                        !event.shiftKey &&
                        !event.nativeEvent.isComposing
                      ) {
                        event.preventDefault();
                        void submitQuestion(question);
                      }
                    }}
                    placeholder="Hỏi theo số hiệu, điều khoản, lĩnh vực hoặc tình huống…"
                    aria-label="Câu hỏi pháp luật"
                  />
                  <div className="composer-footer">
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        render={<Button variant="ghost" size="sm" />}
                      >
                        <FileSearch />{' '}
                        {mode === 'fast' ? 'Tra cứu nhanh' : 'Tra cứu sâu'}{' '}
                        <ChevronDown />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="start">
                        <DropdownMenuItem onClick={() => setMode('fast')}>
                          <Check
                            className={mode === 'fast' ? '' : 'invisible'}
                          />{' '}
                          Nhanh · 6 đoạn
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setMode('deep')}>
                          <Check
                            className={mode === 'deep' ? '' : 'invisible'}
                          />{' '}
                          Sâu · 10 đoạn
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                    <div>
                      <span>Enter để gửi · Shift+Enter xuống dòng</span>
                      <Button
                        size="icon"
                        onClick={() => void submitQuestion(question)}
                        disabled={asking || question.trim().length < 4}
                        aria-label="Gửi câu hỏi"
                      >
                        {asking ? (
                          <LoaderCircle className="spin" />
                        ) : (
                          <ArrowUp />
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
                <p className="legal-disclaimer">
                  Thông tin hỗ trợ tra cứu, không thay thế tư vấn pháp lý. Luôn
                  kiểm tra hiệu lực tại nguồn chính thức.
                </p>
              </div>
            </main>
            <aside className="legal-right-panel">{panelEvidence}</aside>
          </div>
        </div>

        <Sheet open={sourcesSheet} onOpenChange={setSourcesSheet}>
          <SheetContent side="left" className="legal-mobile-sheet">
            <SheetHeader>
              <SheetTitle>Nguồn pháp luật</SheetTitle>
            </SheetHeader>
            {panelSources}
          </SheetContent>
        </Sheet>
        <Sheet open={evidenceSheet} onOpenChange={setEvidenceSheet}>
          <SheetContent side="right" className="legal-mobile-sheet">
            <SheetHeader>
              <SheetTitle>Căn cứ truy hồi</SheetTitle>
            </SheetHeader>
            {panelEvidence}
          </SheetContent>
        </Sheet>

        <Dialog
          open={uploadOpen}
          onOpenChange={(open) => !uploadBusy && setUploadOpen(open)}
        >
          <DialogContent className="legal-upload-dialog">
            <DialogHeader>
              <DialogTitle>Thêm tài liệu vào LuatRAG</DialogTitle>
              <DialogDescription>
                Tệp được gửi tới máy chủ để trích xuất và lập chỉ mục bằng CPU.
                Tệp gốc và text/chunks được lưu trong kho riêng của tài khoản;
                Gemini không tham gia bước đọc tệp.
              </DialogDescription>
            </DialogHeader>
            <input
              ref={fileInput}
              type="file"
              hidden
              accept=".pdf,.docx,.pptx,.xlsx,.txt,.md,.csv"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleFile(file);
                event.currentTarget.value = '';
              }}
            />
            <button
              type="button"
              className={`legal-dropzone ${dragging ? 'is-dragging' : ''}`}
              disabled={uploadBusy}
              onClick={() => fileInput.current?.click()}
              onDragEnter={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                const file = event.dataTransfer.files[0];
                if (file) void handleFile(file);
              }}
            >
              <UploadCloud size={27} />
              <strong>Thả tệp hoặc chọn từ máy</strong>
              <span>PDF, DOCX, PPTX, XLSX, TXT, MD, CSV · tối đa 10 MB</span>
            </button>
            <div className="legal-upload-state">
              <div>
                <span>{uploadStage}</span>
                <strong>{uploadProgress}%</strong>
              </div>
              <Progress value={uploadProgress} />
            </div>
            <div className="legal-upload-note">
              <ShieldCheck size={16} />
              <p>
                PDF scan không có text sẽ được từ chối và yêu cầu OCR trước. Khi
                bạn đặt câu hỏi có đủ căn cứ, chỉ câu hỏi và tối đa 6–10 đoạn đã
                truy hồi mới được gửi tới Gemini để tổng hợp.
              </p>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                disabled={uploadBusy}
                onClick={() => setUploadOpen(false)}
              >
                Đóng
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
          <DialogContent className="legal-history-dialog">
            <DialogHeader>
              <DialogTitle>Lịch sử tra cứu</DialogTitle>
              <DialogDescription>
                Các cuộc trao đổi được lưu trong kho dữ liệu theo tài khoản đang
                đăng nhập.
              </DialogDescription>
            </DialogHeader>
            <ScrollArea className="history-scroll">
              {conversations.length ? (
                conversations.map((item) => (
                  <button
                    type="button"
                    className="history-row"
                    key={item.id}
                    onClick={() => void loadConversation(item.id)}
                  >
                    <span>
                      <Clock3 size={15} />
                      {new Date(item.updated_at).toLocaleDateString('vi-VN')}
                    </span>
                    <strong>{item.title}</strong>
                  </button>
                ))
              ) : (
                <div className="legal-empty-history">
                  <Archive /> Chưa có cuộc trao đổi đã lưu.
                </div>
              )}
            </ScrollArea>
          </DialogContent>
        </Dialog>

        <Dialog open={infoOpen} onOpenChange={setInfoOpen}>
          <DialogContent className="legal-info-dialog">
            <DialogHeader>
              <DialogTitle>Phạm vi và quyền riêng tư</DialogTitle>
              <DialogDescription>
                LuatRAG được thiết kế để giải thích được đường đi từ câu hỏi đến
                căn cứ.
              </DialogDescription>
            </DialogHeader>
            <div className="legal-info-grid">
              <div>
                <span className="info-icon">
                  <Database />
                </span>
                <div>
                  <strong>Corpus pháp luật Việt Nam</strong>
                  <p>
                    {corpus
                      ? `${sources.filter((source) => source.builtin).length} văn bản bootstrap từ ${corpus.dataset} do ${corpus.creator} công bố, snapshot ${corpus.snapshotDate}. Toàn văn được đối chiếu lại từ cổng VBPL; corpus đã được chọn lọc, làm sạch và chia đoạn.`
                      : 'Đang tải thông tin corpus…'}
                  </p>
                  {corpus && (
                    <>
                      <a href={corpus.source} target="_blank" rel="noreferrer">
                        Xem dataset <ExternalLink />
                      </a>{' '}
                      <a
                        href={corpus.licenseUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {corpus.license} <ExternalLink />
                      </a>
                    </>
                  )}
                </div>
              </div>
              <div>
                <span className="info-icon">
                  <Gauge />
                </span>
                <div>
                  <strong>Truy hồi không dùng LLM</strong>
                  <p>
                    Parser OpenXML/PDF, chuẩn hóa tiếng Việt, FTS5/BM25 và
                    reranking đều chạy bằng thuật toán xác định.
                  </p>
                </div>
              </div>
              <div>
                <span className="info-icon">
                  <Sparkles />
                </span>
                <div>
                  <strong>Gemini có ranh giới rõ</strong>
                  <p>
                    Chỉ nhận câu hỏi và tối đa 6–10 đoạn đã truy hồi để tổng
                    hợp; không bật Search, File Search, embeddings hay công cụ
                    bên ngoài.
                  </p>
                </div>
              </div>
            </div>
            <DialogFooter>
              {corpus && (
                <Button
                  variant="outline"
                  render={
                    <a href={corpus.upstream} target="_blank" rel="noreferrer">
                      Mở VBPL.vn <ExternalLink />
                    </a>
                  }
                />
              )}
              <Button onClick={() => setInfoOpen(false)}>Đã hiểu</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <AlertDialog
          open={Boolean(deleteTarget)}
          onOpenChange={(open) => !open && setDeleteTarget(undefined)}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Xóa nguồn này?</AlertDialogTitle>
              <AlertDialogDescription>
                Tệp gốc, bản trích xuất và toàn bộ chỉ mục liên quan sẽ bị xóa
                khỏi kho tài liệu. Các cuộc trao đổi đã sử dụng nguồn này cũng
                bị xóa để không lưu lại trích đoạn. Hành động này không thể hoàn
                tác.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Giữ lại</AlertDialogCancel>
              <AlertDialogAction
                variant="destructive"
                onClick={() => void confirmDelete()}
              >
                Xóa vĩnh viễn
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </Toaster>
    </TooltipProvider>
  );
}
