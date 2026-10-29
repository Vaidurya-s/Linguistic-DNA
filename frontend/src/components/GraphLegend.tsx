import { EDGE_STYLES, GROUP_COLORS, OTHER_GROUP_COLOR } from './edgeStyles.ts'

const SHOWN = [
  'inherited_form',
  'borrowed_from',
  'etymon',
  'derived_form',
  'has_component',
  'variant_of',
  'related_form',
]

export default function GraphLegend() {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-700" aria-label="Graph legend">
      {SHOWN.map((type) => {
        const s = EDGE_STYLES[type]
        return (
          <span key={type} className="flex items-center gap-1.5">
            <svg width="28" height="8" aria-hidden="true">
              <line
                x1="0" y1="4" x2="28" y2="4" stroke={s.color} strokeWidth="2.5"
                strokeDasharray={s.line === 'dotted' ? '2 3' : s.line === 'dashed' ? '6 4' : undefined}
              />
            </svg>
            {s.short}
          </span>
        )
      })}
      {Object.entries(GROUP_COLORS).map(([group, color]) => (
        <span key={group} className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-4 rounded-sm border border-slate-500" style={{ background: color }} />
          {group}
        </span>
      ))}
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-4 rounded-sm border border-slate-500" style={{ background: OTHER_GROUP_COLOR }} />
        other / proto-language
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-4 rounded-sm border border-dashed border-slate-600" />
        <em>reconstructed (*)</em>
      </span>
    </div>
  )
}
