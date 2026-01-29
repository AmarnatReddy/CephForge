import type { LucideIcon } from 'lucide-react'

interface MetricCardProps {
  title: string
  value: string | number
  total?: number
  icon: LucideIcon
  color: 'purple' | 'blue' | 'emerald' | 'amber' | 'red'
  subtitle?: string
}

const colorClasses = {
  purple: {
    bg: 'bg-purple-500/20',
    text: 'text-purple-400',
    border: 'border-purple-500/20',
  },
  blue: {
    bg: 'bg-blue-500/20',
    text: 'text-blue-400',
    border: 'border-blue-500/20',
  },
  emerald: {
    bg: 'bg-emerald-500/20',
    text: 'text-emerald-400',
    border: 'border-emerald-500/20',
  },
  amber: {
    bg: 'bg-amber-500/20',
    text: 'text-amber-400',
    border: 'border-amber-500/20',
  },
  red: {
    bg: 'bg-red-500/20',
    text: 'text-red-400',
    border: 'border-red-500/20',
  },
}

export default function MetricCard({
  title,
  value,
  total,
  icon: Icon,
  color,
  subtitle,
}: MetricCardProps) {
  const colors = colorClasses[color]

  return (
    <div className={`card card-hover p-6`}>
      <div className="flex items-start justify-between mb-4">
        <div className={`w-12 h-12 rounded-xl ${colors.bg} flex items-center justify-center`}>
          <Icon className={`w-6 h-6 ${colors.text}`} />
        </div>
      </div>
      <div>
        <p className="text-sm text-dark-400 mb-1">{title}</p>
        <p className="text-3xl font-bold text-white">
          {value}
          {total !== undefined && (
            <span className="text-lg text-dark-500">/{total}</span>
          )}
        </p>
        {subtitle && (
          <p className="text-xs text-dark-500 mt-1">{subtitle}</p>
        )}
      </div>
    </div>
  )
}
