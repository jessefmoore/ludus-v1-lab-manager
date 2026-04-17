import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import CommandPalette from "./CommandPalette";

export default function AppLayout() {
  return (
    <div className="flex h-screen bg-bg-base">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-auto pl-0 md:pl-0">
        <Outlet />
      </main>
      <CommandPalette />
    </div>
  );
}
