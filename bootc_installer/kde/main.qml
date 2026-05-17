import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    title: i18n("bootc Installer")

    width: 1000
    height: 600
    minimumWidth: 800
    minimumHeight: 600

    onClosing: (close) => {
        // Handle close request
        Qt.quit()
    }

    pageStack.initialPage: welcomePage

    Component {
        id: welcomePage
        Kirigami.ScrollablePage {
            title: i18n("Welcome to bootc Installer")

            ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing

                Kirigami.Heading {
                    level: 1
                    text: i18n("Welcome to bootc Installer")
                }

                Controls.Label {
                    text: i18n("This installer will help you install TunaOS and other bootc-based operating systems to your computer.")
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                Kirigami.FormLayout {
                    Layout.fillWidth: true

                    Controls.Label {
                        Kirigami.FormData.label: i18n("System Information:")
                        text: i18n("Loading system information...")
                    }
                }

                Item {
                    Layout.fillHeight: true
                }

                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Layout.fillWidth: true

                    Item {
                        Layout.fillWidth: true
                    }

                    Controls.Button {
                        text: i18n("Next")
                        icon.name: "go-next"
                        onClicked: {
                            root.pageStack.push(diskPage)
                        }
                    }
                }
            }
        }
    }

    Component {
        id: diskPage
        Kirigami.ScrollablePage {
            title: i18n("Select Installation Disk")
            leftPadding: 0
            rightPadding: 0
            topPadding: 0
            bottomPadding: 0

            ColumnLayout {
                spacing: 0
                anchors.fill: parent

                Kirigami.Heading {
                    level: 2
                    text: i18n("Select the disk to install to")
                    padding: Kirigami.Units.largeSpacing
                    Layout.fillWidth: true
                }

                Controls.Label {
                    text: i18n("This will erase all data on the selected disk. Please make sure you have backed up your data.")
                    wrapMode: Text.WordWrap
                    padding: Kirigami.Units.largeSpacing
                    Layout.fillWidth: true
                    color: Kirigami.Theme.negativeTextColor
                }

                Controls.ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ListView {
                        model: ListModel {
                            id: diskModel
                        }
                        delegate: ItemDelegate {
                            width: ListView.view.width
                            text: model.display
                        }
                    }
                }

                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    padding: Kirigami.Units.largeSpacing
                    Layout.fillWidth: true

                    Controls.Button {
                        text: i18n("Back")
                        icon.name: "go-previous"
                        onClicked: {
                            root.pageStack.pop()
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    Controls.Button {
                        text: i18n("Next")
                        icon.name: "go-next"
                        onClicked: {
                            root.pageStack.push(progressPage)
                        }
                    }
                }
            }
        }
    }

    Component {
        id: progressPage
        Kirigami.ScrollablePage {
            title: i18n("Installation Progress")

            ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing

                Kirigami.Heading {
                    level: 2
                    text: i18n("Installation in progress...")
                }

                Controls.ProgressBar {
                    from: 0
                    to: 100
                    value: 50
                    Layout.fillWidth: true
                }

                Controls.TextArea {
                    readOnly: true
                    text: i18n("Installation output will appear here...")
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                }

                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Layout.fillWidth: true

                    Item {
                        Layout.fillWidth: true
                    }

                    Controls.Button {
                        text: i18n("Cancel")
                        icon.name: "dialog-cancel"
                        enabled: false
                    }
                }
            }
        }
    }
}
