terraform {
  required_version = ">= 1.6.0"
  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.6"
    }
  }
}

provider "github" {
  owner = "LuciferDataEngineer"
}

variable "repository_name" {
  type    = string
  default = "rba-rate-shock-copilot"
}

# Validated in CI. Applying needs a GitHub token and is not part of the build.
resource "github_repository" "copilot" {
  name        = var.repository_name
  description = "What the RBA is saying about the 2026 rate rises, and what each rise costs a mortgage."
  visibility  = "public"
  has_issues  = true
  has_wiki    = false

  topics = ["rba", "monetary-policy", "open-data"]
}

resource "github_repository_pages" "copilot" {
  repository = github_repository.copilot.name
  build_type = "workflow"

  source {
    branch = "main"
    path   = "/"
  }
}
