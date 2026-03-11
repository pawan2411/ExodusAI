terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Artifact Registry for Docker images
resource "google_artifact_registry_repository" "exodusai" {
  location      = var.region
  repository_id = "exodusai"
  format        = "DOCKER"
  description   = "ExodusAI Docker images"
}

# Secret Manager secrets
resource "google_secret_manager_secret" "google_api_key" {
  secret_id = "exodusai-google-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "routes_api_key" {
  secret_id = "exodusai-routes-api-key"
  replication {
    auto {}
  }
}

# Cloud Run service
resource "google_cloud_run_v2_service" "backend" {
  name     = var.service_name
  location = var.region

  template {
    session_affinity = true
    timeout          = "3600s"

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/exodusai/backend:${var.image_tag}"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "FEED_MODE"
        value = "simulation"
      }

      env {
        name  = "TRAFFIC_MODE"
        value = "mock"
      }

      env {
        name = "GOOGLE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.google_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "ROUTES_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.routes_api_key.secret_id
            version = "latest"
          }
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }
  }

  depends_on = [
    google_artifact_registry_repository.exodusai,
  ]
}

# Allow unauthenticated access (for demo)
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Outputs
output "backend_url" {
  value       = google_cloud_run_v2_service.backend.uri
  description = "URL of the deployed ExodusAI backend"
}

output "artifact_registry" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/exodusai"
  description = "Artifact Registry path for Docker images"
}
