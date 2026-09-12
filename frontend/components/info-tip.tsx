'use client'

import { HelpCircle } from 'lucide-react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { GLOSSARY } from '@/lib/presentation'

interface InfoTipProps {
  /** Key into the glossary, e.g. "momentum". */
  entry: keyof typeof GLOSSARY
}

/**
 * A small "what does this mean?" affordance next to any technical term.
 *
 * This is the mechanism that lets the app stay genuinely beginner-friendly
 * without dumbing things down: the surface stays plain-English, and the real
 * indicator name plus its definition are one hover or tap away.
 *
 * It is a real <button> so it is keyboard-reachable and announced to screen
 * readers, rather than a decorative icon that only works on hover.
 */
export function InfoTip({ entry }: InfoTipProps) {
  const { term, plain } = GLOSSARY[entry]

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={`What is ${term}?`}
          className="text-muted-foreground/70 hover:text-foreground rounded-full transition-colors"
        >
          <HelpCircle className="size-3.5" aria-hidden />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <p className="font-semibold">{term}</p>
        <p className="mt-1 text-xs leading-relaxed opacity-90">{plain}</p>
      </TooltipContent>
    </Tooltip>
  )
}
