import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { hfApi } from "@/lib/api-endpoints";
import type { HfCookbookResponse, HfModelDetail } from "@/lib/types";
import { ModelList } from "@/components/models/ModelList";
import { ModelDetail } from "@/components/models/ModelDetail";

const DEFAULT_CONTEXT = 8192;

export default function ModelsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedRepo = searchParams.get("repo");

  // Left pane (catalog list)
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(10);
  const [contextTokens, setContextTokens] = useState(DEFAULT_CONTEXT);
  const [listData, setListData] = useState<HfCookbookResponse | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listPending, setListPending] = useState(false);
  const [listError, setListError] = useState(false);

  // Right pane (model detail)
  const [detail, setDetail] = useState<HfModelDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState(false);

  // Monotonic request ids — a stale response (older search/repo) is dropped.
  const listSeq = useRef(0);
  const detailSeq = useRef(0);
  // URL-driven repo changes clear the detail during render (React's
  // adjust-state-when-props-change pattern) so the previous repo's detail
  // never paints under the new selection; context-token refetches keep it.
  const [prevRepo, setPrevRepo] = useState(selectedRepo);
  if (prevRepo !== selectedRepo) {
    setPrevRepo(selectedRepo);
    setDetail(null);
    setDetailLoading(true);
    setDetailError(false);
  }

  const loadList = useCallback((q: string, lim: number, tokens: number) => {
    const seq = ++listSeq.current;
    return hfApi
      .models(q, lim, tokens)
      .then((res) => {
        if (seq !== listSeq.current) return;
        setListData(res);
        setListError(false);
      })
      .catch(() => {
        if (seq === listSeq.current) setListError(true);
      })
      .finally(() => {
        if (seq === listSeq.current) {
          setListLoading(false);
          setListPending(false);
        }
      });
  }, []);

  const loadDetail = useCallback((repoId: string, tokens: number) => {
    if (!repoId) return;
    const seq = ++detailSeq.current;
    return hfApi
      .detail(repoId, tokens)
      .then((res) => {
        if (seq !== detailSeq.current) return;
        setDetail(res);
        setDetailError(false);
      })
      .catch(() => {
        if (seq === detailSeq.current) {
          // The latest request failed — drop any stale detail so the error
          // state renders instead of silently showing out-of-date data.
          setDetail(null);
          setDetailError(true);
        }
      })
      .finally(() => {
        if (seq === detailSeq.current) setDetailLoading(false);
      });
  }, []);

  useEffect(() => {
    void loadList(query, limit, contextTokens);
  }, [query, limit, contextTokens, loadList]);

  useEffect(() => {
    void loadDetail(selectedRepo ?? "", contextTokens);
  }, [selectedRepo, contextTokens, loadDetail]);

  const handleSearch = () => {
    const q = search.trim();
    setListError(false);
    setListLoading(true);
    setListPending(true);
    if (q === query) {
      // Same query — the list effect won't re-fire, so fetch directly.
      void loadList(q, limit, contextTokens);
    } else {
      setQuery(q);
    }
  };

  const handleRetryList = () => {
    setListError(false);
    setListLoading(true);
    setListPending(true);
    void loadList(query, limit, contextTokens);
  };

  const handleRetryDetail = () => {
    setDetailLoading(true);
    setDetailError(false);
    void loadDetail(selectedRepo ?? "", contextTokens);
  };

  const handleContextChange = (tokens: number) => {
    // Keep the current detail visible but flip loading on — the pane shows
    // the refreshing indicator instead of presenting stale fit data as fresh.
    setContextTokens(tokens);
    setDetailLoading(true);
    setDetailError(false);
  };

  const handleSelect = (repoId: string) => {
    // Clear immediately so the old repo's detail never paints under the new
    // selection; the effect refetches once the URL lands.
    setDetail(null);
    setDetailLoading(true);
    setDetailError(false);
    if (repoId === selectedRepo) {
      // Same repo — the URL won't change, so the detail effect won't re-fire.
      void loadDetail(repoId, contextTokens);
    } else {
      setSearchParams({ repo: repoId });
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-border px-6 py-4 max-md:pl-14">
        <div>
          <h1 className="text-2xl text-text-primary">Models</h1>
          <p className="text-sm text-text-secondary">Browse Hugging Face models and check VRAM fit</p>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-hidden">
        <div className="grid h-full min-h-0 grid-cols-[minmax(320px,380px)_1fr] max-lg:grid-cols-1 max-lg:overflow-y-auto">
          <div className="min-h-0 overflow-y-auto border-r border-border max-lg:overflow-visible max-lg:border-r-0 max-lg:border-b">
            <ModelList
              models={listData?.models ?? []}
              loading={listLoading}
              pending={listPending}
              error={listError}
              search={search}
              onSearchChange={setSearch}
              limit={limit}
              onLimitChange={setLimit}
              onSubmit={handleSearch}
              onRetry={handleRetryList}
              selectedRepo={selectedRepo}
              onSelect={handleSelect}
            />
          </div>
          <div className="min-h-0 overflow-y-auto max-lg:overflow-visible">
            <ModelDetail
              repoId={selectedRepo}
              detail={detail}
              loading={detailLoading}
              error={detailError}
              contextTokens={contextTokens}
              onContextChange={handleContextChange}
              onRetry={handleRetryDetail}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
