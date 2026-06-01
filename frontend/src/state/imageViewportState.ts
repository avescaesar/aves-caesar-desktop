export class ImageViewportState {
	public zoom = 1;
	public panX = 0;
	public panY = 0;
	public cursorX: number | null = null;
	public cursorY: number | null = null;


	public reset(clearCursor = true): void {
		this.zoom = 1;
		this.panX = 0;
		this.panY = 0;
		if (!clearCursor) {
			return;
		}

		this.cursorX = null;
		this.cursorY = null;
	}


	public setCursor(stageX: number, stageY: number): void {
		this.cursorX = stageX;
		this.cursorY = stageY;
	}


	public zoomAt(stageX: number, stageY: number, deltaY: number, stageWidth: number, stageHeight: number, maxZoom: number): void {
		const previousZoom = this.zoom;
		const zoomLimit = Math.max(1, maxZoom);
		const nextZoom = Math.min(zoomLimit, Math.max(1, previousZoom * (deltaY < 0 ? 1.18 : 1 / 1.18)));
		if (nextZoom === previousZoom) {
			return;
		}

		if (Math.abs(nextZoom - 1) < 0.001) {
			this.reset(false);
			return;
		}

		const imageX = (stageX - this.panX) / previousZoom;
		const imageY = (stageY - this.panY) / previousZoom;
		this.zoom = nextZoom;
		this.panX = stageX - imageX * nextZoom;
		this.panY = stageY - imageY * nextZoom;
		this.clamp(stageWidth, stageHeight);
	}


	public zoomToActualSizeAt(stageX: number, stageY: number, stageWidth: number, stageHeight: number, imageWidth: number, imageHeight: number): void {
		if (this.zoom > 1.001) {
			this.reset(false);
			return;
		}

		const previousZoom = this.zoom;
		const nextZoom = Math.max(1, imageWidth / stageWidth, imageHeight / stageHeight);
		if (Math.abs(nextZoom - 1) < 0.001) {
			this.reset(false);
			return;
		}

		const imageX = (stageX - this.panX) / previousZoom;
		const imageY = (stageY - this.panY) / previousZoom;
		this.zoom = nextZoom;
		this.panX = stageX - imageX * nextZoom;
		this.panY = stageY - imageY * nextZoom;
		this.clamp(stageWidth, stageHeight);
	}


	public panBy(deltaX: number, deltaY: number, stageWidth: number, stageHeight: number): void {
		if (this.zoom <= 1) {
			return;
		}

		this.panX += deltaX;
		this.panY += deltaY;
		this.clamp(stageWidth, stageHeight);
	}


	public clamp(stageWidth: number, stageHeight: number): void {
		if (this.zoom <= 1 || stageWidth <= 0 || stageHeight <= 0) {
			this.reset(false);
			return;
		}

		const minPanX = stageWidth - stageWidth * this.zoom;
		const minPanY = stageHeight - stageHeight * this.zoom;
		this.panX = Math.min(0, Math.max(minPanX, this.panX));
		this.panY = Math.min(0, Math.max(minPanY, this.panY));
	}
}
