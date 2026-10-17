import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import OrbApp from "./components/OrbApp";
import { desktop, ORB_MODE } from "./lib/desktop";
import { useArgus } from "./lib/store";
import "./styles.css";

// The desktop shell gets its own chrome (draggable header, room for the
// native window controls); the floating orb is a separate, transparent page.
if (desktop) document.documentElement.classList.add("desktop");
if (ORB_MODE) document.documentElement.classList.add("orb-mode");

// Handy in devtools and for the desktop acceptance test.
(window as unknown as { __argusStore: typeof useArgus }).__argusStore = useArgus;

createRoot(document.getElementById("root")!).render(
  <StrictMode>{ORB_MODE ? <OrbApp /> : <App />}</StrictMode>
);
