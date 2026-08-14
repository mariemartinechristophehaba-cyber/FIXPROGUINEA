type Variant = 'success' | 'warning' | 'danger' | 'neutral' | 'info';

const map: Record<Variant, string> = {
  success: 'bg-success/10 text-success border-success/20',
  warning: 'bg-warning/10 text-warning border-warning/20',
  danger: 'bg-danger/10 text-danger border-danger/20',
  neutral: 'bg-white/5 text-muted border-white/10',
  info: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
};

export default function StatusBadge({ children, variant = 'neutral' }: { children: React.ReactNode; variant?: Variant }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${map[variant]}`}>
      {children}
    </span>
  );
}
