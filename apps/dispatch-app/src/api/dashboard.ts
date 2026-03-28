import { apiRequest } from "./client";
import { withDefaults } from "../utils/defaults";
import type {
  DashboardHealth,
  DashboardSessionsResponse,
  DashboardTasksResponse,
  DashboardSkillsResponse,
  DashboardEventsResponse,
  DashboardCcuResponse,
} from "./types";

// ---------------------------------------------------------------------------
// Default values for defensive access
// ---------------------------------------------------------------------------

const DEFAULT_HEALTH: DashboardHealth = {
  daemon_pid: null,
  daemon_running: false,
  uptime_seconds: 0,
  active_sessions: 0,
  total_sessions: 0,
  total_bus_events: 0,
  total_sdk_events: 0,
  events_last_hour: 0,
  sdk_events_last_hour: 0,
  last_event_age_seconds: null,
  health_status: "unknown",
  active_reminders: 0,
  facts_count: 0,
  skills_count: 0,
};

const DEFAULT_SESSIONS_RESPONSE: DashboardSessionsResponse = {
  sessions: [],
  total: 0,
  by_tier: {},
};

const DEFAULT_TASKS_RESPONSE: DashboardTasksResponse = {
  reminders: [],
  recent_task_events: [],
};

const DEFAULT_SKILLS_RESPONSE: DashboardSkillsResponse = {
  skills: [],
  total: 0,
};

const DEFAULT_EVENTS_RESPONSE: DashboardEventsResponse = {
  events: [],
  total_count: 0,
  max_offset: 0,
};

const DEFAULT_CCU_RESPONSE: DashboardCcuResponse = {
  active_block: null,
  recent_blocks: [],
  daily: [],
  daily_totals: {},
  quota: null,
  _loading: false,
  _updated_at: null,
  _error: null,
  _quota_error: null,
};

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/** Fetch system health snapshot */
export async function getDashboardHealth(): Promise<DashboardHealth> {
  const data = await apiRequest<Partial<DashboardHealth>>(
    "/api/dashboard/health",
  );
  return withDefaults(DEFAULT_HEALTH, data);
}

/** Fetch all active sessions */
export async function getDashboardSessions(): Promise<DashboardSessionsResponse> {
  const data = await apiRequest<Partial<DashboardSessionsResponse>>(
    "/api/dashboard/sessions",
  );
  return withDefaults(DEFAULT_SESSIONS_RESPONSE, data);
}

/** Fetch Claude Code Usage (quota data). */
export async function getDashboardCcu(): Promise<DashboardCcuResponse> {
  const data = await apiRequest<Partial<DashboardCcuResponse>>(
    "/api/dashboard/ccu",
  );
  return withDefaults(DEFAULT_CCU_RESPONSE, data);
}

/** Fetch tasks and reminders */
export async function getDashboardTasks(): Promise<DashboardTasksResponse> {
  const data = await apiRequest<Partial<DashboardTasksResponse>>(
    "/api/dashboard/tasks",
  );
  return withDefaults(DEFAULT_TASKS_RESPONSE, data);
}

/** Fetch bus events */
export async function getDashboardEvents(
  limit = 100,
): Promise<DashboardEventsResponse> {
  const data = await apiRequest<Partial<DashboardEventsResponse>>(
    "/api/dashboard/events",
    { params: { limit } },
  );
  return withDefaults(DEFAULT_EVENTS_RESPONSE, data);
}

/** Fetch skills list */
export async function getDashboardSkills(): Promise<DashboardSkillsResponse> {
  const data = await apiRequest<Partial<DashboardSkillsResponse>>(
    "/api/dashboard/skills",
  );
  return withDefaults(DEFAULT_SKILLS_RESPONSE, data);
}
