pipeline {
    agent { label 'linux' }

    options {
        timeout(time: 60, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '10'))
        disableConcurrentBuilds()
    }

    parameters {
        choice(name: 'TEST_ENV', choices: ['dongying', 'liaohuibao', 'huiqubao'], description: '执行项目（对应 config/environments/<项目>/ 目录）')
        string(name: 'MARKERS', defaultValue: 'smoke', description: 'pytest 标记，如 smoke 或 "login or inventory"，留空执行全部')
        booleanParam(name: 'HEADED', defaultValue: false, description: '有头模式（CI 环境请保持关闭）')
        string(name: 'WORKERS', defaultValue: '4', description: '并发进程数，0 表示串行')
    }

    environment {
        PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'
        PYTHONUNBUFFERED = '1'
        HEADLESS = 'true'
    }

    stages {
        stage('准备环境') {
            steps {
                sh 'python3 -m venv .venv'
                sh '.venv/bin/pip install -r requirements.txt'
                sh '.venv/bin/playwright install --with-deps chromium'
            }
        }

        stage('执行 UI 自动化') {
            steps {
                script {
                    def pytestArgs = ".venv/bin/pytest --env=${params.TEST_ENV}"
                    if (params.MARKERS?.trim()) {
                        pytestArgs += " -m \"${params.MARKERS}\""
                    }
                    if (params.HEADED) {
                        pytestArgs += " --headed"
                    }
                    if (params.WORKERS?.isInteger() && params.WORKERS.toInteger() > 0) {
                        pytestArgs += " -n ${params.WORKERS}"
                    }
                    sh pytestArgs
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'reports/**, logs/**', allowEmptyArchive: true
            junit testResults: 'reports/junit.xml', allowEmptyResults: true
            // 已安装 Allure Jenkins 插件时启用，自动生成并发布 Allure 报告
            // allure includeProperties: false, results: [[path: 'reports/allure-results']]
        }
    }
}
