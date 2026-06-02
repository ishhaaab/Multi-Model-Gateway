import { useId } from "react";
import { cn } from "@/lib/utils";

interface SliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  /** Optional captions shown under the track, e.g. ["Precise", "Creative"]. */
  endLabels?: [string, string];
  hint?: string;
  className?: string;
  disabled?: boolean;
}

export function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  endLabels,
  hint,
  className,
  disabled,
}: SliderProps) {
  const id = useId();
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 0;

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-sm font-medium text-text-secondary">
          {label}
        </label>
        <span className="rounded-md border border-border bg-bg-tertiary px-2 py-0.5 font-mono text-[0.8125rem] text-text-primary tabular-nums">
          {value}
        </span>
      </div>
      <input
        id={id}
        type="range"
        className="gw-slider"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{
          background: `linear-gradient(to right, var(--color-accent-primary) ${pct}%, var(--color-bg-tertiary) ${pct}%)`,
        }}
      />
      {endLabels && (
        <div className="flex justify-between text-[0.75rem] text-text-muted">
          <span>{endLabels[0]}</span>
          <span>{endLabels[1]}</span>
        </div>
      )}
      {hint && <span className="text-[0.75rem] text-text-muted">{hint}</span>}
    </div>
  );
}
