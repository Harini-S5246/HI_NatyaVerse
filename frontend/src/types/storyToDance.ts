export interface StoryToDanceStoryRequest {
  story_text: string
  language: string
  title?: string
}

export interface MudraMapping {
  concept: string
  mudra: string | null
  meaning: string | null
  source: string | null
  status: 'mapped' | 'unsupported' | 'knowledge_unavailable'
  note: string | null
}

export interface BhavaMapping {
  expressive_quality: string
  bhava: string | null
  status: 'unmapped'
  note: string
}

export interface DanceVisualReference {
  category: 'mudra' | 'bhava' | 'pose'
  status: 'matched' | 'unavailable'
  source_type?: 'analyzed_video' | 'project_dataset' | 'unavailable'
  reference_status?: 'model_predicted' | 'dataset_labelled' | 'expert_verified' | 'unavailable'
  concept: string | null
  predicted_label: string | null
  dataset_label?: string | null
  confidence: number | null
  confidence_threshold: number
  video_id: string | null
  frame_number: number | null
  timestamp: number | null
  frame_filename: string | null
  image_url: string | null
  original_frame_url: string | null
  asset_id?: string | null
  dataset_name?: string | null
  dataset_relative_path?: string | null
  evidence_status: string
  crop_status: string
  unavailable_reason: string | null
  reused_in_scenes?: string[]
}

export interface SceneVisualReferenceRequest {
  scene_id: string
  mudra_label: string | null
  bhava_label: string | null
  pose_label: string | null
}

export interface SceneVisualReferences {
  scene_id: string
  mudra: DanceVisualReference
  bhava: DanceVisualReference
  pose: DanceVisualReference
  confidence_threshold: number
}

export interface MovementIntent {
  action: string
  target: string | null
  direction: string | null
  actions: MovementIntentAction[]
  movement_name: string | null
  movement_type: string | null
  status: 'supported' | 'review_required' | 'unavailable'
  source: string | null
  source_reference: string | null
  movement_concept: string | null
  candidate_adavu: string | null
  mapping_status: 'supported_concept' | 'review_required' | 'unavailable'
  mapping_reason: string | null
  source_quote: string | null
  review_required: boolean
}

export interface MovementIntentAction {
  action: string
  target: string | null
  direction: string | null
  movement_type: string
  movement_concept: string | null
  candidate_adavu: null
  status: 'supported' | 'review_required'
  mapping_status: 'supported_concept' | 'review_required'
  source: string | null
  source_reference: string | null
  mapping_reason: string
  review_required: boolean
}

export interface BharatanatyamConcept {
  action: string
  direction: string | null
  concept: string
  candidate_adavu: null
  mapping_status: 'supported_concept'
  source: string
  source_reference: string
  mapping_reason: string
}

export interface MovementSourceProvenance {
  concept: string
  source: string
  source_reference: string
  notes: string
}

export interface MovementVocabulary {
  status: 'supported' | 'review_required' | 'unavailable'
  message: string
  entries: Array<Record<string, string | string[] | null>>
  source: string | null
  supported_actions: string[]
  supported_intents: string[]
  directions: string[]
}

export interface MovementMapping {
  action_type: string
  movement_primitive: string | null
  adavu: string | null
  pose: string | null
  status: 'review_required'
  note: string
  movement_intent: MovementIntent | null
  movement_name: string | null
  movement_source: string | null
  movement_vocabulary: MovementVocabulary | null
}

export interface DanceScene {
  scene_id: string
  story_id: string
  order: number
  scene_order: number
  characters: string[]
  character: string[]
  action_type: string
  action_text: string
  action: string
  objects: string[]
  location: string | null
  expressive_qualities: string[]
  expressions: string[]
  narrative_text: string
  source_text: string
  duration_estimate_seconds: number | null
  visualization_sequence: string[]
  mudra: MudraMapping[]
  bhava: BhavaMapping[]
  movement_intent: MovementIntent
  bharatanatyam_concept: BharatanatyamConcept[]
  candidate_adavu: null
  mapping_status: 'supported_concept' | 'review_required'
  source_provenance: MovementSourceProvenance[]
  generator_label: null
  generation_status: 'unavailable'
  dance_mapping: {
    mudra_status: 'mapped' | 'unsupported' | 'knowledge_unavailable'
    mudras: MudraMapping[]
    bhava: BhavaMapping[]
    movement: MovementMapping
  }
}

export interface ChoreographyStep {
  step_id: string
  scene_id: string
  order: number
  characters: string[]
  source_quote: string
  story_action: string
  objects: string[]
  location: string | null
  source_expressions: string[]
  mudras: MudraMapping[]
  bhava: BhavaMapping[]
  visualization_sequence: string[]
  movement_primitive: null
  adavu: null
  pose: null
  movement_status: 'review_required'
  movement_note: string
  movement_intent: MovementIntent | null
  movement_name: string | null
  movement_source: string | null
  movement_vocabulary: MovementVocabulary | null
  transition: Record<string, string>
}

export interface DancePlan {
  story_id: string
  dance_plan_id: string
  choreography_id: string
  title: string
  language: string
  summary: string
  status: 'ready'
  scenes: DanceScene[]
  choreography: ChoreographyStep[]
  movement_vocabulary: MovementVocabulary | null
  pose_sequence: {
    status: 'not_generated'
    items: Array<Record<string, string>>
    message: string
  }
  generated_performance: {
    status: 'not_generated'
    video_url: null
    message: string
  }
  limitations: string[]
}

export interface DanceGenerationSceneStatus {
  scene_id: string
  scene_order: number
  status: 'generated' | 'unavailable' | 'review_required'
  generator_label: string | null
  mapping_status: 'supported_concept' | 'review_required'
  movement_concepts: string[]
  candidate_adavu: null
  movement_sequence: string[]
  mudra: string[]
  action: string
  target: string | null
  direction: string | null
  transition: string
  expressive_state: 'neutral' | 'respectful' | 'admiration' | 'attention' | 'graceful'
  source_provenance: MovementSourceProvenance[]
  start_frame_index: number | null
  end_frame_index: number | null
  start_time_seconds: number | null
  end_time_seconds: number | null
  reason: string | null
}

export interface DanceGenerationSceneTiming {
  scene_id: string
  scene_order: number
  start_time_seconds: number
  end_time_seconds: number
}

export interface DanceGenerationResult {
  generation_id: string
  story_id: string
  dance_plan_id: string
  choreography_id: string
  status: 'completed' | 'unavailable' | 'failed'
  fps: number | null
  duration_seconds: number | null
  video_width: number | null
  video_height: number | null
  frame_count: number | null
  skeleton_format: string | null
  coordinate_convention: string | null
  pose_sequence: Array<{
    frame_index: number
    timestamp_seconds: number
    pose_data: Record<string, unknown>
  }> | null
  video_url: string | null
  scene_timings: DanceGenerationSceneTiming[]
  movement_coverage: {
    generated_scenes: number
    total_scenes: number
    source_supported_scenes: number
  }
  generator_name: string | null
  generator_version: string | null
  visualization_type: 'procedural_dancer_avatar' | 'rigged_3d_humanoid' | null
  scenes: DanceGenerationSceneStatus[]
  provenance: string[]
  reason: string | null
  error_code:
    | 'MODEL_UNAVAILABLE'
    | 'CHECKPOINT_UNAVAILABLE'
    | 'GENERATION_FAILED'
    | 'VIDEO_RENDER_FAILED'
    | 'VIDEO_VALIDATION_FAILED'
    | 'STALE_GENERATION'
    | 'INVALID_GENERATION_OUTPUT'
    | null
  limitations: string[]
}

export interface StoryToDanceRecord {
  story_id: string
  title: string
  language: string
  story_text: string
  status: 'ready_for_planning' | 'plan_ready'
  created_at: string
  dance_plan: DancePlan | null
}

export interface StoryToDanceWorkflowResponse {
  story: StoryToDanceRecord
  generation: DanceGenerationResult
}
