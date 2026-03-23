import { apiRequest } from "./client";

export interface Skill {
  name: string;
  description: string;
  path: string;
  has_scripts: boolean;
  script_count: number;
  scripts: string[];
  file_count: number;
}

interface SkillsResponse {
  skills: Skill[];
  total: number;
}

/** List all available skills. GET /api/dashboard/skills */
export async function getSkills(): Promise<Skill[]> {
  const res = await apiRequest<SkillsResponse>("/api/dashboard/skills");
  return res.skills;
}
