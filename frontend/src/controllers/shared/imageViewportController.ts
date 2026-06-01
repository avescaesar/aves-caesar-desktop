import { DetectionState } from "../../state/detectionState";
import { ImageViewportState } from "../../state/imageViewportState";
import type { EventBinder } from "../core/eventBinder";

export class ImageViewportController {
	private imagePanLastClientX: number | null = null;
	private imagePanLastClientY: number | null = null;
	private imagePanPointerId: number | null = null;
	private lastPointerClientX: number | null = null;
	private lastPointerClientY: number | null = null;


	public constructor(public readonly state: ImageViewportState, private readonly detectionState: DetectionState) {}


	public bindEvents(bindEvent: EventBinder): void {
		const imageStage = document.querySelector<HTMLElement>("[data-image-stage]");
		bindEvent(imageStage, "pointerdown", event => this.handlePointerDown(event as PointerEvent));
		bindEvent(imageStage, "pointermove", event => this.handlePointerMove(event as PointerEvent));
		bindEvent(imageStage, "pointerup", event => this.handlePointerEnd(event as PointerEvent));
		bindEvent(imageStage, "pointercancel", event => this.handlePointerEnd(event as PointerEvent));
		bindEvent(imageStage, "mousemove", event => this.handleMouseMove(event as MouseEvent));
		bindEvent(imageStage, "wheel", event => this.handleWheel(event as WheelEvent), { passive: false });
	}


	public fitStageIfNeeded(): void {
		const stage = document.querySelector<HTMLElement>("[data-image-stage]");
		if (!stage || stage.style.width) {
			return;
		}

		this.fitStage();
	}


	public fitStage(): void {
		if (!this.detectionState.result) {
			return;
		}

		window.requestAnimationFrame(() => {
			const panel = document.querySelector<HTMLElement>(".image-panel");
			const stage = document.querySelector<HTMLElement>(".image-stage");
			if (!panel || !stage || !this.detectionState.result) {
				return;
			}

			const panelRect = panel.getBoundingClientRect();
			const availableWidth = panel.clientWidth;
			const availableHeight = Math.max(240, window.innerHeight - panelRect.top - 22);
			const ratio = this.detectionState.result.width / this.detectionState.result.height;
			let displayWidth = Math.min(availableWidth, availableHeight * ratio);
			let displayHeight = displayWidth / ratio;
			if (displayHeight > availableHeight) {
				displayHeight = availableHeight;
				displayWidth = displayHeight * ratio;
			}

			stage.style.width = `${Math.floor(displayWidth)}px`;
			stage.style.height = `${Math.floor(displayHeight)}px`;
			this.state.clamp(Math.floor(displayWidth), Math.floor(displayHeight));
			this.applyZoomLayerTransform();
		});
	}


	public handleGlobalKeyDown(event: KeyboardEvent): void {
		if (this.isTypingTarget(event.target)) {
			return;
		}

		if (event.code !== "Space" || event.repeat) {
			return;
		}

		const stage = document.querySelector<HTMLElement>("[data-image-stage]");
		if (!stage || !this.detectionState.result) {
			return;
		}

		event.preventDefault();
		const rect = stage.getBoundingClientRect();
		const stagePoint = this.imageStagePoint(stage, rect);
		const stageX = stagePoint.x;
		const stageY = stagePoint.y;
		this.state.setCursor(stageX, stageY);
		this.state.zoomToActualSizeAt(stageX, stageY, rect.width, rect.height, this.detectionState.result.width, this.detectionState.result.height);
		this.applyZoomLayerTransform();
	}


	public storePointerPosition(event: MouseEvent): void {
		this.lastPointerClientX = event.clientX;
		this.lastPointerClientY = event.clientY;
	}


	private handlePointerDown(event: PointerEvent): void {
		const stage = event.currentTarget;
		if (!(stage instanceof HTMLElement) || event.button !== 0 || this.state.zoom <= 1.001 || this.isImageControlTarget(event.target)) {
			return;
		}

		event.preventDefault();
		this.imagePanPointerId = event.pointerId;
		this.imagePanLastClientX = event.clientX;
		this.imagePanLastClientY = event.clientY;
		stage.setPointerCapture(event.pointerId);
		stage.classList.add("is-panning");
	}


	private handlePointerMove(event: PointerEvent): void {
		const stage = event.currentTarget;
		if (!(stage instanceof HTMLElement) || this.imagePanPointerId !== event.pointerId || this.imagePanLastClientX === null || this.imagePanLastClientY === null) {
			return;
		}

		event.preventDefault();
		this.storePointerPosition(event);
		const rect = stage.getBoundingClientRect();
		this.state.setCursor(event.clientX - rect.left, event.clientY - rect.top);
		this.state.panBy(event.clientX - this.imagePanLastClientX, event.clientY - this.imagePanLastClientY, rect.width, rect.height);
		this.imagePanLastClientX = event.clientX;
		this.imagePanLastClientY = event.clientY;
		this.applyZoomLayerTransform();
	}


	private handlePointerEnd(event: PointerEvent): void {
		const stage = event.currentTarget;
		if (!(stage instanceof HTMLElement) || this.imagePanPointerId !== event.pointerId) {
			return;
		}

		if (stage.hasPointerCapture(event.pointerId)) {
			stage.releasePointerCapture(event.pointerId);
		}

		this.imagePanPointerId = null;
		this.imagePanLastClientX = null;
		this.imagePanLastClientY = null;
		stage.classList.remove("is-panning");
	}


	private handleWheel(event: WheelEvent): void {
		const stage = event.currentTarget;
		if (!(stage instanceof HTMLElement) || !this.detectionState.result) {
			return;
		}

		event.preventDefault();
		const rect = stage.getBoundingClientRect();
		const stageX = event.clientX - rect.left;
		const stageY = event.clientY - rect.top;
		const maxZoom = Math.max(this.detectionState.result.width / rect.width, this.detectionState.result.height / rect.height);
		this.state.setCursor(stageX, stageY);
		this.state.zoomAt(stageX, stageY, event.deltaY, rect.width, rect.height, maxZoom);
		this.applyZoomLayerTransform();
	}


	private handleMouseMove(event: MouseEvent): void {
		const stage = event.currentTarget;
		if (!(stage instanceof HTMLElement)) {
			return;
		}

		this.storePointerPosition(event);
		const rect = stage.getBoundingClientRect();
		this.state.setCursor(event.clientX - rect.left, event.clientY - rect.top);
	}


	private imageStagePoint(stage: HTMLElement, rect: DOMRect): { x: number; y: number } {
		if (this.lastPointerClientX !== null && this.lastPointerClientY !== null && this.lastPointerClientX >= rect.left && this.lastPointerClientX <= rect.right && this.lastPointerClientY >= rect.top && this.lastPointerClientY <= rect.bottom) {
			return {
				x: this.lastPointerClientX - rect.left,
				y: this.lastPointerClientY - rect.top,
			};
		}

		if (this.state.cursorX !== null && this.state.cursorY !== null) {
			return {
				x: Math.min(rect.width, Math.max(0, this.state.cursorX)),
				y: Math.min(rect.height, Math.max(0, this.state.cursorY)),
			};
		}

		return {
			x: stage.clientWidth / 2,
			y: stage.clientHeight / 2,
		};
	}


	private isTypingTarget(target: EventTarget | null): boolean {
		if (!(target instanceof HTMLElement)) {
			return false;
		}

		return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target.isContentEditable;
	}


	private isImageControlTarget(target: EventTarget | null): boolean {
		return target instanceof Element && target.closest("button, input, select, textarea, a") !== null;
	}


	private applyZoomLayerTransform(): void {
		const layer = document.querySelector<HTMLElement>("[data-image-zoom-layer]");
		const stage = layer?.closest<HTMLElement>("[data-image-stage]");
		if (!layer || !stage) {
			return;
		}

		layer.style.width = `${Math.floor(stage.clientWidth * this.state.zoom)}px`;
		layer.style.height = `${Math.floor(stage.clientHeight * this.state.zoom)}px`;
		layer.style.transform = `translate(${this.state.panX}px, ${this.state.panY}px)`;
		stage.classList.toggle("is-pannable", this.state.zoom > 1.001);
	}
}
