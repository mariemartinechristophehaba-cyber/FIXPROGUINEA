export default function Header({ title }: { title: string }) {
  return (
    <header className="sticky top-0 z-10 bg-background/80 backdrop-blur border-b border-border px-6 py-4">
      <h2 className="text-xl font-medium">{title}</h2>
    </header>
  );
}
