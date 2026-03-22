import { useEffect, useState } from "react";
import { subscribeUnreadAgentCount } from "../state/unreadAgents";

/** React hook that returns the current unread agent session count. */
export function useUnreadAgentCount(): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    return subscribeUnreadAgentCount(setCount);
  }, []);

  return count;
}
