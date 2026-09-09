"use client";

import { useEffect } from "react";

const REPLACEMENTS: Array<[string | RegExp, string]> = [
  ["ARA Advanced Analytics", "GRID Pro"],
  ["Advanced CFF Analytics", "GRID Pro"],
  ["CFF Advanced Analytics", "GRID Pro"],
  ["Advanced CFF", "GRID Pro"],
  ["ARA Ratings", "GRID Adj. Net"],
  ["CFF Ratings", "GRID Adj. Net"],
  ["CollegeFootballFocus", "GRID"],
  ["College Football Focus", "GRID"],
  ["Adjusted Ratings & Analytics", "College Football Analytics"],
  ["AdjEM", "Adj. Net"],
  [/AdjO(?!ff)/g, "Adj. Off"],
  [/AdjD(?!ef)/g, "Adj. Def"],
];

function replaceBrandTerms(value: string) {
  const trimmed = value.trim();
  if (trimmed === "CFF") return value.replace("CFF", "Adj. Net");
  if (trimmed === "ARA") return value.replace("ARA", "GRID");
  return REPLACEMENTS.reduce((next, [from, to]) => next.replaceAll(from, to), value);
}

function shouldSkip(node: Node) {
  const parent = node.parentElement;
  return !!parent?.closest("script, style, code, pre, textarea, [data-preserve-model-key]");
}

function updateNode(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) {
    if (shouldSkip(root)) return;
    const current = root.nodeValue || "";
    const next = replaceBrandTerms(current);
    if (next !== current) root.nodeValue = next;
    return;
  }

  if (!(root instanceof Element)) return;

  ["aria-label", "title", "alt"].forEach((attribute) => {
    const current = root.getAttribute(attribute);
    if (!current) return;
    const next = replaceBrandTerms(current);
    if (next !== current) root.setAttribute(attribute, next);
  });

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    updateNode(node);
    node = walker.nextNode();
  }

  root.querySelectorAll("[aria-label], [title], [alt]").forEach((element) => {
    ["aria-label", "title", "alt"].forEach((attribute) => {
      const current = element.getAttribute(attribute);
      if (!current) return;
      const next = replaceBrandTerms(current);
      if (next !== current) element.setAttribute(attribute, next);
    });
  });
}

export default function GridTerminologyGuard() {
  useEffect(() => {
    updateNode(document.body);

    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === "characterData") {
          updateNode(mutation.target);
          return;
        }
        mutation.addedNodes.forEach(updateNode);
      });
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    return () => observer.disconnect();
  }, []);

  return null;
}
