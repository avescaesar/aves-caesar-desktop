export function escapeHtml(value: string): string {
	return value.replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[char] ?? char));
}


export function errorMessage(error: unknown): string {
	return error instanceof Error ? error.message : String(error);
}


export function fileName(path: string): string {
	return path.split(/[\\/]/).pop() || path;
}


export function formatPercentWhole(value: number): string {
	return `${Math.round(value * 100)}%`;
}


export function formatElapsedSeconds(value: number): string {
	return value < 10 ? `${value.toFixed(1)}s` : `${Math.round(value)}s`;
}


export function formatRemainingDuration(valueMs: number): string {
	const totalMinutes = Math.ceil(Math.max(0, valueMs) / 60000);
	if (totalMinutes <= 0) {
		return "< 1 min";
	}

	if (totalMinutes < 60) {
		return `${totalMinutes} min`;
	}

	const hours = Math.floor(totalMinutes / 60);
	const minutes = totalMinutes % 60;
	return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`;
}


export function formatTimeOfDay(value: Date): string {
	const hours = String(value.getHours()).padStart(2, "0");
	const minutes = String(value.getMinutes()).padStart(2, "0");
	return `${hours}:${minutes}`;
}


export function delay(ms: number): Promise<void> {
	return new Promise(resolve => window.setTimeout(resolve, ms));
}
