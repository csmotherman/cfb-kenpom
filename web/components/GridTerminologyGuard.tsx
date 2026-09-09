"use client";

import { useEffect } from "react";

const REPLACEMENTS: Array<[string | RegExp, string]> = [
  ["GRID AdjNet college football ratings table", "GRID Relative Performance Ratings table"],
  ["GRID AdjNet", "GRID Relative Performance Ratings"],
  ["AdjNet Ratings", "Relative Performance Ratings"],
  ["Adjusted Net Rating", "Relative Performance Rating"],
  ["Opponent-Adjusted College Football Ratings", "Relative Performance Ratings"],
  ["Overall Rating", "adjNet"],
  ["Offense Rating", "adjOff"],
  ["Defense Rating", "adjDef"],
  ["ARA Advanced Analytics", "GRID Pro"],
  ["Advanced CFF Analytics", "GRID Pro"],
  ["CFF Advanced Analytics", "GRID Pro"],
  ["Advanced CFF", "GRID Pro"],
  ["ARA Ratings", "GRID Relative Performance Ratings"],
  ["CFF Ratings", "GRID Relative Performance Ratings"],
  ["CollegeFootballFocus", "GRID"],
  ["College Football Focus", "GRID"],
  ["Adjusted Ratings & Analytics", "College Football Analytics"],
  ["AdjEM", "adjNet"],
  ["AdjNet", "adjNet"],
  [/AdjO(?!ff)/g, "adjOff"],
  ["AdjOff", "adjOff"],
  [/AdjD(?!ef)/g, "adjDef"],
  ["AdjDef", "adjDef"],
];

function replaceBrandTerms(value: string) {
  const trimmed = value.trim();
  if (trimmed === "CFF") return value.replace("CFF", "adjNet");
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
    updateNode(document.documentElement);

    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === "characterData") {
          updateNode(mutation.target);
          return;
        }
        mutation.addedNodes.forEach(updateNode);
      });
    });

    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    return () => observer.disconnect();
  }, []);

  return null;
}
