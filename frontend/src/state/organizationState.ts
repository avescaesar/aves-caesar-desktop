import type { OrganizationJobStatus } from "../types";

export class OrganizationState {
	public sourceDirectory = "";
	public destinationDirectory = "";
	public gpxPaths: string[] = [];
	public renameFiles = true;
	public recursive = true;
	public activeJobId: string | null = null;
	public status: OrganizationJobStatus | null = null;
	public modalOpen = false;
	public confirmNonEmptyOpen = false;
	public error = "";
	public startedAtMs: number | null = null;


	public canRun(): boolean {
		return Boolean(this.sourceDirectory.trim() && this.destinationDirectory.trim() && !this.activeJobId);
	}


	public start(jobId: string): void {
		this.activeJobId = jobId;
		this.modalOpen = true;
		this.error = "";
		this.startedAtMs = Date.now();
		this.status = { state: "running", total: 0, completed: 0, copied: 0, errors: 0, currentFile: "", message: "" };
	}


	public applyStatus(status: OrganizationJobStatus): void {
		this.status = status;
		this.error = status.state === "error" ? status.error || status.message : "";
		if (status.state !== "running") {
			this.activeJobId = null;
		}
	}


	public estimatedFinishMs(nowMs = Date.now()): number | null {
		if (!this.status || this.status.state !== "running" || this.startedAtMs === null) {
			return null;
		}

		if (this.status.total <= 0 || this.status.completed <= 0 || this.status.completed >= this.status.total) {
			return null;
		}

		const elapsedMs = nowMs - this.startedAtMs;
		if (elapsedMs <= 0) {
			return null;
		}

		const averageMsPerImage = elapsedMs / this.status.completed;
		const remainingImages = this.status.total - this.status.completed;
		return nowMs + averageMsPerImage * remainingImages;
	}
}
