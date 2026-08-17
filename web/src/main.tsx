import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "../design-input/theme.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
