import type { LightroomInfo } from "../types";

export class LightroomState {
	public info: LightroomInfo | null = null;
	public busy = false;
	public message = "";
	public upgradePromptOpen = false;
	public upgradeError = "";
}
