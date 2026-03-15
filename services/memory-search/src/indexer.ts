/**
 * File indexing for different content types.
 */

import { existsSync, readFileSync, statSync, readdirSync } from "fs";
import { join, basename, extname, relative } from "path";
import { homedir } from "os";
import { Glob } from "bun";
import { Store, hashContent } from "./store";
import { CategoryConfig, expandPath } from "./config";

// =============================================================================
// Types
// =============================================================================

export interface IndexResult {
  added: number;
  updated: number;
  removed: number;
  errors: string[];
}

export interface DocumentToIndex {
  path: string;
  title: string;
  content: string;
  mtime: number;
}

// =============================================================================
// Text Extraction
// =============================================================================

function extractTitle(content: string, filepath: string): string {
  // Try to extract title from markdown heading
  const headingMatch = content.match(/^#\s+(.+)$/m);
  if (headingMatch) {
    return headingMatch[1].trim();
  }

  // Try YAML frontmatter title
  const frontmatterMatch = content.match(/^---\n[\s\S]*?title:\s*["']?([^"'\n]+)["']?[\s\S]*?---/);
  if (frontmatterMatch) {
    return frontmatterMatch[1].trim();
  }

  // Fall back to filename
  return basename(filepath, extname(filepath));
}

// =============================================================================
// Chunking
// =============================================================================

const CHUNK_SIZE_CHARS = 3000;
const CHUNK_OVERLAP_CHARS = 300;

export function chunkDocument(content: string): string[] {
  if (content.length <= CHUNK_SIZE_CHARS) {
    return [content];
  }

  const chunks: string[] = [];
  let start = 0;

  while (start < content.length) {
    let end = start + CHUNK_SIZE_CHARS;

    // Try to break at a paragraph or sentence boundary
    if (end < content.length) {
      // Look for paragraph break
      const paragraphBreak = content.lastIndexOf("\n\n", end);
      if (paragraphBreak > start + CHUNK_SIZE_CHARS / 2) {
        end = paragraphBreak + 2;
      } else {
        // Look for sentence break
        const sentenceBreak = content.lastIndexOf(". ", end);
        if (sentenceBreak > start + CHUNK_SIZE_CHARS / 2) {
          end = sentenceBreak + 2;
        }
      }
    }

    chunks.push(content.slice(start, end).trim());

    // Move start with overlap
    start = end - CHUNK_OVERLAP_CHARS;
    if (start < 0) start = 0;

    // Prevent infinite loop
    if (start >= content.length - 1) break;
  }

  return chunks.filter(c => c.length > 0);
}

// =============================================================================
// File-based Indexer
// =============================================================================

export class FileIndexer {
  private store: Store;

  constructor(store: Store) {
    this.store = store;
  }

  /**
   * Index a directory based on category config
   */
  async indexCategory(category: string, config: CategoryConfig): Promise<IndexResult> {
    const result: IndexResult = { added: 0, updated: 0, removed: 0, errors: [] };

    if (!config.path) {
      result.errors.push(`Category ${category} has no path configured`);
      return result;
    }

    const basePath = expandPath(config.path);
    if (!existsSync(basePath)) {
      result.errors.push(`Path does not exist: ${basePath}`);
      return result;
    }

    const pattern = config.pattern || "**/*";

    // Get all matching files
    const glob = new Glob(pattern);
    const files: string[] = [];

    for await (const file of glob.scan({ cwd: basePath, onlyFiles: true })) {
      files.push(file);
    }

    // Get existing paths in this category
    const existingPaths = new Set(this.store.getAllActivePaths(category));
    const seenPaths = new Set<string>();

    // Index each file
    for (const relPath of files) {
      seenPaths.add(relPath);
      const fullPath = join(basePath, relPath);

      try {
        const stat = statSync(fullPath);
        const mtime = stat.mtimeMs;

        // Check if document exists and is up to date
        const existing = this.store.findDocument(category, relPath);

        if (existing && existing.mtime >= mtime) {
          // Document is up to date
          continue;
        }

        // Read and process file
        const content = readFileSync(fullPath, "utf-8");
        const title = extractTitle(content, relPath);
        const hash = hashContent(content);

        // Store content
        this.store.insertContent(hash, content);

        if (existing) {
          // Update existing document
          this.store.updateDocument(existing.id, title, hash, mtime);
          result.updated++;
        } else {
          // Insert new document
          this.store.insertDocument(category, relPath, title, hash, mtime);
          result.added++;
        }
      } catch (error) {
        result.errors.push(`Error indexing ${fullPath}: ${error}`);
      }
    }

    // Deactivate removed files
    for (const existingPath of existingPaths) {
      if (!seenPaths.has(existingPath)) {
        this.store.deactivateDocument(category, existingPath);
        result.removed++;
      }
    }

    return result;
  }

  /**
   * Index a single file
   */
  indexFile(category: string, fullPath: string, basePath: string): { success: boolean; error?: string } {
    try {
      const relPath = relative(basePath, fullPath);
      const stat = statSync(fullPath);
      const mtime = stat.mtimeMs;

      const content = readFileSync(fullPath, "utf-8");
      const title = extractTitle(content, relPath);
      const hash = hashContent(content);

      this.store.insertContent(hash, content);

      const existing = this.store.findDocument(category, relPath);
      if (existing) {
        this.store.updateDocument(existing.id, title, hash, mtime);
      } else {
        this.store.insertDocument(category, relPath, title, hash, mtime);
      }

      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }
}

// =============================================================================
// JSONL Transcript Indexer
// =============================================================================

export class TranscriptIndexer {
  private store: Store;

  constructor(store: Store) {
    this.store = store;
  }

  /**
   * Index JSONL transcript files (append-only optimization)
   */
  async indexTranscripts(transcriptsPath: string): Promise<IndexResult> {
    const result: IndexResult = { added: 0, updated: 0, removed: 0, errors: [] };
    const basePath = expandPath(transcriptsPath);

    if (!existsSync(basePath)) {
      result.errors.push(`Transcripts path does not exist: ${basePath}`);
      return result;
    }

    // Find all JSONL files
    const glob = new Glob("**/*.jsonl");

    for await (const relPath of glob.scan({ cwd: basePath, onlyFiles: true })) {
      const fullPath = join(basePath, relPath);

      try {
        const stat = statSync(fullPath);
        const mtime = stat.mtimeMs;

        const existing = this.store.findDocument("transcripts", relPath);

        // For append-only, we can skip if mtime hasn't changed
        if (existing && existing.mtime >= mtime) {
          continue;
        }

        // Read and parse JSONL
        const content = readFileSync(fullPath, "utf-8");
        const lines = content.split("\n").filter(l => l.trim());

        // Extract meaningful content from JSONL
        const messages: string[] = [];
        for (const line of lines) {
          try {
            const entry = JSON.parse(line);
            // Extract text content from various message formats
            if (entry.message?.content) {
              const msgContent = entry.message.content;
              if (typeof msgContent === "string") {
                messages.push(msgContent);
              } else if (Array.isArray(msgContent)) {
                for (const part of msgContent) {
                  if (part.type === "text" && part.text) {
                    messages.push(part.text);
                  }
                }
              }
            }
          } catch {
            // Skip invalid JSON lines
          }
        }

        if (messages.length === 0) {
          continue;
        }

        // Combine messages for indexing
        const combinedContent = messages.join("\n\n");
        const title = `Transcript: ${basename(relPath, ".jsonl")}`;
        const hash = hashContent(combinedContent);

        this.store.insertContent(hash, combinedContent);

        if (existing) {
          this.store.updateDocument(existing.id, title, hash, mtime);
          result.updated++;
        } else {
          this.store.insertDocument("transcripts", relPath, title, hash, mtime);
          result.added++;
        }
      } catch (error) {
        result.errors.push(`Error indexing transcript ${fullPath}: ${error}`);
      }
    }

    return result;
  }
}

// =============================================================================
// SMS Indexer (from chat.db)
// =============================================================================

import Database from "bun:sqlite";
import { copyFileSync, unlinkSync, existsSync as fsExistsSync } from "fs";
import { tmpdir } from "os";

const HOME = homedir();
const MESSAGES_DB = join(HOME, "Library/Messages/chat.db");
const MACOS_EPOCH_OFFSET = 978307200;

export class SMSIndexer {
  private store: Store;

  constructor(store: Store) {
    this.store = store;
  }

  /**
   * Index SMS messages from chat.db
   *
   * To avoid lock conflicts with Messages.app, we copy the database to a
   * temp location before reading. This is more reliable than URI flags.
   */
  async indexSMS(): Promise<IndexResult> {
    const result: IndexResult = { added: 0, updated: 0, removed: 0, errors: [] };

    if (!existsSync(MESSAGES_DB)) {
      result.errors.push("Messages database not found");
      return result;
    }

    // Copy to temp location to avoid lock conflicts
    // Must copy WAL files too (chat.db uses WAL mode)
    const timestamp = Date.now();
    const tempDb = join(tmpdir(), `chat-${timestamp}.db`);
    const tempShm = join(tmpdir(), `chat-${timestamp}.db-shm`);
    const tempWal = join(tmpdir(), `chat-${timestamp}.db-wal`);

    try {
      copyFileSync(MESSAGES_DB, tempDb);
      // Copy WAL files if they exist
      const shmPath = MESSAGES_DB + "-shm";
      const walPath = MESSAGES_DB + "-wal";
      if (fsExistsSync(shmPath)) copyFileSync(shmPath, tempShm);
      if (fsExistsSync(walPath)) copyFileSync(walPath, tempWal);

      const db = new Database(tempDb, { readonly: true });

      // Get all chats
      const chats = db.query(`
        SELECT chat_identifier, display_name
        FROM chat
        WHERE chat_identifier IS NOT NULL
      `).all() as { chat_identifier: string; display_name: string | null }[];

      for (const chat of chats) {
        const chatId = chat.chat_identifier;

        // Get messages for this chat
        const messages = db.query(`
          SELECT
            m.text,
            m.attributedBody,
            m.date,
            m.is_from_me,
            h.id as sender
          FROM message m
          LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
          LEFT JOIN chat c ON cmj.chat_id = c.ROWID
          LEFT JOIN handle h ON m.handle_id = h.ROWID
          WHERE c.chat_identifier = ?
          ORDER BY m.date ASC
        `).all(chatId) as {
          text: string | null;
          attributedBody: Buffer | null;
          date: number;
          is_from_me: number;
          sender: string | null;
        }[];

        if (messages.length === 0) continue;

        // Extract message texts
        const texts: string[] = [];
        let latestDate = 0;

        for (const msg of messages) {
          let text = msg.text;

          // Extract from attributedBody if needed
          if (!text && msg.attributedBody) {
            text = this.parseAttributedBody(msg.attributedBody);
          }

          if (text && text.trim()) {
            const sender = msg.is_from_me ? "me" : (msg.sender || "unknown");
            texts.push(`[${sender}]: ${text}`);
          }

          if (msg.date > latestDate) {
            latestDate = msg.date;
          }
        }

        if (texts.length === 0) continue;

        const content = texts.join("\n");
        const title = chat.display_name || `Chat: ${chatId}`;
        const hash = hashContent(content);
        const mtime = latestDate / 1e9 + MACOS_EPOCH_OFFSET;

        // Check if chat already indexed
        const existing = this.store.findDocument("sms", chatId);

        this.store.insertContent(hash, content);

        if (existing) {
          if (existing.hash !== hash) {
            this.store.updateDocument(existing.id, title, hash, mtime);
            result.updated++;
          }
        } else {
          this.store.insertDocument("sms", chatId, title, hash, mtime);
          result.added++;
        }
      }

      db.close();
    } catch (error) {
      result.errors.push(`Error indexing SMS: ${error}`);
    } finally {
      // Clean up temp files (main db + WAL files)
      try {
        if (fsExistsSync(tempDb)) unlinkSync(tempDb);
        if (fsExistsSync(tempShm)) unlinkSync(tempShm);
        if (fsExistsSync(tempWal)) unlinkSync(tempWal);
      } catch {
        // Ignore cleanup errors
      }
    }

    return result;
  }

  private parseAttributedBody(blob: Buffer): string | null {
    try {
      // The attributedBody is a binary plist with NSAttributedString
      // We can try to extract plain text by looking for readable strings
      const str = blob.toString("utf-8");

      // Look for the actual text content after streamtyped markers
      const match = str.match(/NSString.*?\x01(.+?)(?:\x00|\x04|$)/s);
      if (match) {
        return match[1].replace(/[\x00-\x1f]/g, "").trim();
      }

      // Fallback: extract any readable ASCII
      const readable = str.replace(/[^\x20-\x7e\n]/g, "").trim();
      return readable.length > 0 ? readable : null;
    } catch {
      return null;
    }
  }
}

// =============================================================================
// Contacts Notes Indexer
// =============================================================================

export class ContactsIndexer {
  private store: Store;

  constructor(store: Store) {
    this.store = store;
  }

  /**
   * Index contact notes from macOS Contacts
   */
  async indexContacts(): Promise<IndexResult> {
    const result: IndexResult = { added: 0, updated: 0, removed: 0, errors: [] };

    try {
      // Use contacts CLI to get notes
      const proc = Bun.spawn(["bash", "-c", `${HOME}/.claude/skills/contacts/scripts/contacts list --json 2>/dev/null || echo "[]"`], {
        stdout: "pipe",
      });

      const output = await new Response(proc.stdout).text();
      await proc.exited;

      let contacts: { name: string; notes?: string; phone?: string }[];
      try {
        contacts = JSON.parse(output);
      } catch {
        contacts = [];
      }

      for (const contact of contacts) {
        if (!contact.notes || !contact.notes.trim()) continue;

        const path = contact.phone || contact.name;
        const content = `Contact: ${contact.name}\n\nNotes:\n${contact.notes}`;
        const title = `Contact Notes: ${contact.name}`;
        const hash = hashContent(content);
        const mtime = Date.now();

        const existing = this.store.findDocument("contacts", path);

        this.store.insertContent(hash, content);

        if (existing) {
          if (existing.hash !== hash) {
            this.store.updateDocument(existing.id, title, hash, mtime);
            result.updated++;
          }
        } else {
          this.store.insertDocument("contacts", path, title, hash, mtime);
          result.added++;
        }
      }
    } catch (error) {
      result.errors.push(`Error indexing contacts: ${error}`);
    }

    return result;
  }
}
