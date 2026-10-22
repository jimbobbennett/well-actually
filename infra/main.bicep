@description('Globally unique Azure Container Registry name.')
param registryName string = 'wellactuallydemo2026'

@description('Name of the dedicated identity used by Container Apps to pull the image.')
param identityName string = 'well-actually-acr-pull'

@description('Name of the Consumption managed environment.')
param environmentName string = 'well-actually-demo-env'

@description('Name of the public dashboard Container App.')
param containerAppName string = 'well-actually-dashboard'

@description('Immutable tag of the image already pushed to the registry.')
param imageTag string = 'demo-2026-10-22-amd64'

@description('Set true only after the dashboard image has been pushed to the registry.')
param provisionDashboard bool = false

@secure()
@description('Tiger Cloud PostgreSQL connection string, stored as a Container App secret.')
param timescaleDbUrl string

param location string = resourceGroup().location

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource pullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, pullIdentity.id, acrPullRoleId)
  scope: registry
  properties: {
    principalId: pullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

resource environment 'Microsoft.App/managedEnvironments@2026-07-01' = if (provisionDashboard) {
  name: environmentName
  location: location
  properties: {}
}

resource dashboard 'Microsoft.App/containerApps@2024-03-01' = if (provisionDashboard) {
  name: containerAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${pullIdentity.id}': {}
    }
  }
  properties: {
    environmentId: environment!.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        allowInsecure: false
        transport: 'auto'
        traffic: [
          {
            weight: 100
            latestRevision: true
          }
        ]
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: pullIdentity.id
        }
      ]
      secrets: [
        {
          name: 'timescaledb-url'
          value: timescaleDbUrl
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'dashboard'
          image: '${registry.properties.loginServer}/well-actually-dashboard:${imageTag}'
          env: [
            {
              name: 'TIMESCALEDB_URL'
              secretRef: 'timescaledb-url'
            }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 1
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 30
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/'
                port: 8000
                scheme: 'HTTP'
              }
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/'
                port: 8000
                scheme: 'HTTP'
              }
              periodSeconds: 10
              timeoutSeconds: 3
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    acrPullRole
  ]
}

output registryLoginServer string = registry.properties.loginServer
output pullIdentityResourceId string = pullIdentity.id
output dashboardUrl string = provisionDashboard
  ? 'https://${dashboard!.properties.configuration.ingress.fqdn}'
  : ''
