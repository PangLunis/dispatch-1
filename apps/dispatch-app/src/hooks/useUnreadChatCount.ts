import { useEffect, useState } from "react";
import { subscribeUnreadChatCount } from "../state/unreadChats";

/** React hook that returns the current unread chat count. */
export function useUnreadChatCount(): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    return subscribeUnreadChatCount(setCount);
  }, []);

  return count;
}
