import { useImageStore } from "@/stores/image-store";
import { getImageDisplayUrl, formatRelativeTime, truncate } from "@/lib/utils";

/** Recent image generations for the left sidebar (Image mode). */
export function ImageHistoryList() {
  const history = useImageStore((s) => s.history);

  if (history.length === 0) {
    return <p className="px-3 py-8 text-center text-sm text-text-muted">No images yet</p>;
  }

  return (
    <ul className="flex flex-col gap-0.5 py-1">
      {history.map((h, i) => {
        const thumb = h.images[0];
        const url = thumb ? getImageDisplayUrl(thumb.url) : null;
        return (
          <li
            key={h.promptId + h.createdAt}
            className="animate-slide-up"
            style={{ animationDelay: `${Math.min(i, 12) * 30}ms` }}
          >
            <a
              href={url ?? undefined}
              target="_blank"
              rel="noopener noreferrer"
              title={h.prompt}
              className="group flex items-center gap-2.5 rounded-lg border-l-2 border-transparent px-2 py-1.5 transition-colors hover:bg-bg-tertiary/60"
            >
              {url ? (
                <img
                  src={url}
                  alt=""
                  loading="lazy"
                  className="h-10 w-10 shrink-0 rounded-md border border-border object-cover"
                />
              ) : (
                <span className="h-10 w-10 shrink-0 rounded-md border border-border bg-bg-tertiary" />
              )}
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate text-sm text-text-primary">{truncate(h.prompt, 30)}</span>
                <span className="text-[0.7rem] text-text-muted">
                  {formatRelativeTime(new Date(h.createdAt).toISOString())}
                </span>
              </span>
            </a>
          </li>
        );
      })}
    </ul>
  );
}
