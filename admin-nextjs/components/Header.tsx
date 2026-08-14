import Notifications from './Notifications';

export default function Header({ title }: { title: string }) {
  return (
    <header className="sticky top-0 z-10 bg-zinc-950/80 backdrop-blur border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
      <h2 className="text-xl font-medium">{title}</h2>
      <Notifications />
    </header>
  );
}
