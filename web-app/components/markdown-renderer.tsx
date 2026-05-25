'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'
import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { cn } from '@/lib/utils'

// ─── Code block with copy button ─────────────────────────────────────────────

function CodeBlock({ children, className }: { children: string; className?: string }) {
  const [copied, setCopied] = useState(false)

  function copy() {
    navigator.clipboard.writeText(children).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const lang = className?.replace('language-', '') ?? ''

  return (
    <div className="group/code relative my-3 rounded-lg border border-border bg-muted overflow-hidden">
      {lang && (
        <div className="flex items-center justify-between px-4 py-1.5 border-b border-border bg-muted/60">
          <span className="text-xs font-mono text-muted-foreground">{lang}</span>
          <button
            onClick={copy}
            aria-label="Copy code"
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      )}
      {!lang && (
        <button
          onClick={copy}
          aria-label="Copy code"
          className="absolute top-2 right-2 hidden group-hover/code:flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors bg-muted rounded px-1.5 py-0.5"
        >
          {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      )}
      <pre className="overflow-x-auto px-4 py-3 text-sm font-mono text-foreground leading-relaxed">
        <code>{children}</code>
      </pre>
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

interface MarkdownRendererProps {
  content: string
  className?: string
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div className={cn('prose-sm leading-relaxed', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={{
        // Paragraphs
        p({ children }) {
          return <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
        },
        // Headings
        h1({ children }) {
          return <h1 className="text-lg font-bold mt-4 mb-2 first:mt-0">{children}</h1>
        },
        h2({ children }) {
          return <h2 className="text-base font-bold mt-3 mb-1.5 first:mt-0">{children}</h2>
        },
        h3({ children }) {
          return <h3 className="text-sm font-bold mt-2 mb-1 first:mt-0">{children}</h3>
        },
        // Strong / em
        strong({ children }) {
          return <strong className="font-semibold">{children}</strong>
        },
        em({ children }) {
          return <em className="italic">{children}</em>
        },
        // Inline code
        code({ children, className }) {
          const isBlock = className?.startsWith('language-')
          if (isBlock) {
            return (
              <CodeBlock className={className}>
                {String(children).replace(/\n$/, '')}
              </CodeBlock>
            )
          }
          return (
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs text-foreground">
              {children}
            </code>
          )
        },
        // Fenced code blocks
        pre({ children }) {
          // The code element inside handles rendering
          return <>{children}</>
        },
        // Links
        a({ href, children }) {
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 hover:opacity-80 transition-opacity"
            >
              {children}
            </a>
          )
        },
        // Lists
        ul({ children }) {
          return <ul className="my-2 ml-4 list-disc space-y-1">{children}</ul>
        },
        ol({ children }) {
          return <ol className="my-2 ml-4 list-decimal space-y-1">{children}</ol>
        },
        li({ children }) {
          return <li className="leading-relaxed">{children}</li>
        },
        // Blockquote
        blockquote({ children }) {
          return (
            <blockquote className="my-2 border-l-2 border-border pl-3 text-muted-foreground italic">
              {children}
            </blockquote>
          )
        },
        // Horizontal rule
        hr() {
          return <hr className="my-3 border-border" />
        },
        // Table
        table({ children }) {
          return (
            <div className="my-3 overflow-x-auto">
              <table className="w-full text-sm border-collapse">{children}</table>
            </div>
          )
        },
        th({ children }) {
          return (
            <th className="border border-border px-3 py-1.5 text-left font-semibold bg-muted">
              {children}
            </th>
          )
        },
        td({ children }) {
          return <td className="border border-border px-3 py-1.5">{children}</td>
        },
      }}
    >
      {content}
    </ReactMarkdown>
    </div>
  )
}
