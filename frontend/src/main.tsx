import React from 'react'
import ReactDOM from 'react-dom/client'
import { Amplify } from 'aws-amplify'
import App from './App'
import { loadConfig } from './aws-config'
import './index.css'

loadConfig().then(cfg => {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId:       cfg.userPoolId,
        userPoolClientId: cfg.userPoolClientId,
        identityPoolId:   cfg.identityPoolId,
      },
    },
  })

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  )
})
