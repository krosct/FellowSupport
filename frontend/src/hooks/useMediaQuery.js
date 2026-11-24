import { useEffect, useState } from "react";

/** Se a media query vale agora, atualizando quando muda (ex.: girar o celular, ou ligar "reduzir movimento"). */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);
  return matches;
}
