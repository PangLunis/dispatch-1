import React from "react";
import { StyleSheet, Text, View } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { branding } from "../config/branding";

// ---------------------------------------------------------------------------
// Lightweight markdown renderer using only RN Text/View.
// Handles: bold, italic, inline code, code blocks, links (markdown + bare),
// headers, blockquotes, bullet/ordered lists, horizontal rules.
// Avoids the layout/overlay bugs of react-native-markdown-display.
// ---------------------------------------------------------------------------

const URL_RE = /https?:\/\/[^\s<>"'\])},]+/gi;

interface Props {
  children: string;
  /** Called with the maximum line width (px) and line count per text block.
   *  Used by MessageBubble to shrink-wrap single-line bubbles. */
  onMaxLineWidth?: (width: number, lineCount?: number) => void;
}

/** Top-level component: splits text into blocks and renders each. */
export function SimpleMarkdown({ children, onMaxLineWidth }: Props) {
  const blocks = parseBlocks(children);
  return (
    <View>
      {blocks.map((block, i) => (
        <BlockRenderer key={i} block={block} onMaxLineWidth={onMaxLineWidth} />
      ))}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Block-level parsing
// ---------------------------------------------------------------------------

type Block =
  | { type: "paragraph"; text: string }
  | { type: "heading"; level: number; text: string }
  | { type: "code_block"; text: string }
  | { type: "blockquote"; text: string }
  | { type: "hr" }
  | { type: "list_item"; ordered: boolean; index: number; text: string };

function parseBlocks(raw: string): Block[] {
  const lines = raw.split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (/^```/.test(line)) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing ```
      blocks.push({ type: "code_block", text: codeLines.join("\n") });
      continue;
    }

    // Heading
    const headingMatch = /^(#{1,6})\s+(.+)$/.exec(line);
    if (headingMatch) {
      blocks.push({ type: "heading", level: headingMatch[1].length, text: headingMatch[2] });
      i++;
      continue;
    }

    // Horizontal rule
    if (/^\s*(?:[-]{3,}|[*]{3,}|[_]{3,})\s*$/.test(line)) {
      blocks.push({ type: "hr" });
      i++;
      continue;
    }

    // Blockquote
    if (/^\s*>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      blocks.push({ type: "blockquote", text: quoteLines.join("\n") });
      continue;
    }

    // Unordered list item
    const ulMatch = /^\s*[-*+]\s+(.+)$/.exec(line);
    if (ulMatch) {
      blocks.push({ type: "list_item", ordered: false, index: 0, text: ulMatch[1] });
      i++;
      continue;
    }

    // Ordered list item
    const olMatch = /^\s*(\d+)[.)]\s+(.+)$/.exec(line);
    if (olMatch) {
      blocks.push({ type: "list_item", ordered: true, index: parseInt(olMatch[1], 10), text: olMatch[2] });
      i++;
      continue;
    }

    // Empty line
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Paragraph: collect consecutive non-special lines
    const paraLines: string[] = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^```/.test(lines[i]) &&
      !/^#{1,6}\s/.test(lines[i]) &&
      !/^\s*>\s?/.test(lines[i]) &&
      !/^\s*[-*+]\s+/.test(lines[i]) &&
      !/^\s*\d+[.)]\s+/.test(lines[i]) &&
      !/^\s*([-*_])\s*\1\s*\1/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    blocks.push({ type: "paragraph", text: paraLines.join("\n") });
  }

  return blocks;
}

// ---------------------------------------------------------------------------
// Block rendering
// ---------------------------------------------------------------------------

/** Extract max line width and line count from onTextLayout event and report it. */
function makeTextLayoutHandler(onMaxLineWidth?: (width: number, lineCount?: number) => void) {
  if (!onMaxLineWidth) return undefined;
  return (e: { nativeEvent: { lines: Array<{ width: number }> } }) => {
    const lines = e.nativeEvent.lines;
    if (lines.length === 0) return;
    let max = 0;
    for (const line of lines) {
      if (line.width > max) max = line.width;
    }
    onMaxLineWidth(max, lines.length);
  };
}

function BlockRenderer({ block, onMaxLineWidth }: { block: Block; onMaxLineWidth?: (width: number) => void }) {
  const handleTextLayout = makeTextLayoutHandler(onMaxLineWidth);

  switch (block.type) {
    case "paragraph":
      return (
        <Text style={s.paragraph} onTextLayout={handleTextLayout}>
          <InlineRenderer text={block.text} />
        </Text>
      );
    case "heading": {
      const hs =
        block.level === 1 ? s.h1 : block.level === 2 ? s.h2 : s.h3;
      return (
        <Text style={hs} onTextLayout={handleTextLayout}>
          <InlineRenderer text={block.text} />
        </Text>
      );
    }
    case "code_block":
      return (
        <View style={s.codeBlock}>
          <Text style={s.codeBlockText} onTextLayout={handleTextLayout}>{block.text}</Text>
        </View>
      );
    case "blockquote":
      return (
        <View style={s.blockquote}>
          <Text style={s.body} onTextLayout={handleTextLayout}>
            <InlineRenderer text={block.text} />
          </Text>
        </View>
      );
    case "hr":
      return <View style={s.hr} />;
    case "list_item":
      return (
        <View style={s.listItem}>
          <Text style={s.listBullet}>
            {block.ordered ? `${block.index}.` : "•"}
          </Text>
          <Text style={[s.body, s.listText]} onTextLayout={handleTextLayout}>
            <InlineRenderer text={block.text} />
          </Text>
        </View>
      );
  }
}

// ---------------------------------------------------------------------------
// Inline parsing & rendering
// ---------------------------------------------------------------------------

type InlineToken =
  | { type: "text"; value: string }
  | { type: "bold"; value: string }
  | { type: "italic"; value: string }
  | { type: "bold_italic"; value: string }
  | { type: "code"; value: string }
  | { type: "link"; text: string; url: string };

function parseInline(raw: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  // Combined regex for inline elements:
  // 1. Markdown links [text](url)
  // 2. Bold+italic ***text*** or ___text___
  // 3. Bold **text** or __text__
  // 4. Italic *text* or _text_ (not preceded/followed by word chars for _)
  // 5. Inline code `text`
  // 6. Bare URLs
  const re =
    /\[([^\]]+)\]\((https?:\/\/[^)]+)\)|\*\*\*(.+?)\*\*\*|___(.+?)___|\*\*(.+?)\*\*|__(.+?)__|\*(.+?)\*|(?<!\w)_([^_]+?)_(?!\w)|`([^`]+)`|(https?:\/\/[^\s<>"'\])},]+)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(raw)) !== null) {
    // Push preceding text
    if (match.index > lastIndex) {
      tokens.push({ type: "text", value: raw.slice(lastIndex, match.index) });
    }

    if (match[1] != null && match[2] != null) {
      // Markdown link
      tokens.push({ type: "link", text: match[1], url: match[2] });
    } else if (match[3] != null || match[4] != null) {
      // Bold+italic
      tokens.push({ type: "bold_italic", value: match[3] ?? match[4] });
    } else if (match[5] != null || match[6] != null) {
      // Bold
      tokens.push({ type: "bold", value: match[5] ?? match[6] });
    } else if (match[7] != null || match[8] != null) {
      // Italic
      tokens.push({ type: "italic", value: match[7] ?? match[8] });
    } else if (match[9] != null) {
      // Inline code
      tokens.push({ type: "code", value: match[9] });
    } else if (match[10] != null) {
      // Bare URL — strip trailing punctuation
      let url = match[10];
      const trailingPunct = /[.,:;!?)]+$/.exec(url);
      let suffix = "";
      if (trailingPunct) {
        suffix = trailingPunct[0];
        url = url.slice(0, -suffix.length);
      }
      tokens.push({ type: "link", text: url.length > 40 ? url.slice(0, 37) + "..." : url, url });
      if (suffix) {
        tokens.push({ type: "text", value: suffix });
      }
      // Adjust regex position if we trimmed chars
      re.lastIndex = match.index + url.length;
    }

    lastIndex = re.lastIndex;
  }

  // Remaining text
  if (lastIndex < raw.length) {
    tokens.push({ type: "text", value: raw.slice(lastIndex) });
  }

  return tokens;
}

function InlineRenderer({ text }: { text: string }) {
  const tokens = parseInline(text);
  return (
    <>
      {tokens.map((tok, i) => {
        switch (tok.type) {
          case "text":
            return <Text key={i}>{tok.value}</Text>;
          case "bold":
            return (
              <Text key={i} style={s.bold}>
                {tok.value}
              </Text>
            );
          case "italic":
            return (
              <Text key={i} style={s.italic}>
                {tok.value}
              </Text>
            );
          case "bold_italic":
            return (
              <Text key={i} style={s.boldItalic}>
                {tok.value}
              </Text>
            );
          case "code":
            return (
              <Text key={i} style={s.inlineCode}>
                {tok.value}
              </Text>
            );
          case "link":
            return (
              <Text
                key={i}
                style={s.link}
                onPress={() => WebBrowser.openBrowserAsync(tok.url)}
              >
                {tok.text}
              </Text>
            );
        }
      })}
    </>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const s = StyleSheet.create({
  body: {
    color: "#fafafa",
    fontSize: 16,
    lineHeight: 22,
  },
  paragraph: {
    color: "#fafafa",
    fontSize: 16,
    lineHeight: 22,
    marginBottom: 4,
  },
  h1: {
    color: "#fafafa",
    fontSize: 20,
    fontWeight: "700",
    lineHeight: 26,
    marginTop: 8,
    marginBottom: 4,
  },
  h2: {
    color: "#fafafa",
    fontSize: 18,
    fontWeight: "700",
    lineHeight: 24,
    marginTop: 6,
    marginBottom: 4,
  },
  h3: {
    color: "#fafafa",
    fontSize: 16,
    fontWeight: "700",
    lineHeight: 22,
    marginTop: 4,
    marginBottom: 2,
  },
  bold: {
    fontWeight: "700",
    color: "#fafafa",
  },
  italic: {
    fontStyle: "italic",
    color: "#fafafa",
  },
  boldItalic: {
    fontWeight: "700",
    fontStyle: "italic",
    color: "#fafafa",
  },
  inlineCode: {
    backgroundColor: "#1e1e22",
    color: "#e4e4e7",
    fontFamily: "SpaceMono",
    fontSize: 14,
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 4,
  },
  link: {
    color: branding.accentColor,
    textDecorationLine: "underline",
  },
  codeBlock: {
    backgroundColor: "#1e1e22",
    padding: 10,
    borderRadius: 8,
    marginVertical: 4,
  },
  codeBlockText: {
    color: "#e4e4e7",
    fontFamily: "SpaceMono",
    fontSize: 13,
    lineHeight: 18,
  },
  blockquote: {
    backgroundColor: "#1e1e22",
    borderLeftWidth: 3,
    borderLeftColor: "#52525b",
    paddingLeft: 10,
    paddingVertical: 4,
    marginVertical: 4,
  },
  hr: {
    backgroundColor: "#3f3f46",
    height: 1,
    marginVertical: 8,
  },
  listItem: {
    flexDirection: "row",
    marginVertical: 2,
  },
  listBullet: {
    color: "#fafafa",
    fontSize: 16,
    lineHeight: 22,
    width: 20,
  },
  listText: {
    flex: 1,
  },
});
