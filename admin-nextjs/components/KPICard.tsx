type Props = {
  title: string;
  value: string;
  change?: string;
  positive?: boolean;
};

export default function KPICard({ title, value, change, positive = true }: Props) {
  return (
    <div className="bg-surface border border-border rounded-xl p-5 transition-transform hover:-translate-y-0.5 duration-150">
      <div className="text-muted text-sm font-medium">{title}</div>
      <div className="mt-2 text-2xl font-medium">{value}</div>
      {change && (
        <div className={`mt-1 text-sm ${positive ? 'text-success' : 'text-danger'}`}>{change}</div>
      )}
    </div>
  );
}
