import { StrictMode } from 'react';
import { createRoot } from "react-dom/client";
import '../index.scss';
import App from './App';

const root = createRoot(document.getElementById("root") as HTMLElement);
declare global {
  namespace JSX {
    interface IntrinsicElements {
      item: React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>;
    }
  }
}
root.render(
  <StrictMode>
    <App />
  </StrictMode>
);


